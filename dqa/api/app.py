"""FastAPI app factory (LLD 04). Repo, object store, queue and authenticator are injected."""
import hashlib
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Protocol

from fastapi import Depends, FastAPI, File, Header, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from dqa.api import auth
from dqa.api.auth import Authenticator, Principal
from dqa.api.store import ObjectStore
from dqa.ingest.parser import sniff_format
from dqa.models import FindingStatus as Status
from dqa.models import IssueType, Reference, Severity, Source
from dqa.ports import Repo

log = logging.getLogger(__name__)

QUEUE_INGEST = "dqa-ingest"
MAX_LIMIT = 200  # OQ-118
SNIFF_BYTES = 4096


class Enqueue(Protocol):
    def __call__(self, queue: str, message: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class Settings:
    auth_mode: str = "open"  # ADR-023: "open" (no sign-in) | "dev_header" (role-matrix tests)
    env: str = "dev"
    max_upload_bytes: int = 50 * 1024 * 1024  # PROVISIONAL(OQ-104/OQ-118)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict[str, Any] | None = None):
        self.status, self.code, self.message, self.details = status, code, message, details or {}


def _err(request: Request, status: int, code: str, message: str,
         details: dict[str, Any] | None = None) -> JSONResponse:
    body = {"error": {"code": code, "message": message, "details": details or {},
                      "trace_id": getattr(request.state, "trace_id", "")}}
    return JSONResponse(body, status_code=status)


_REF_TYPES = {"allowed_uom", "generic_terms", "uom_aliases", "category_keywords", "taxonomy",
              "manufacturer_aliases", "severity_policy"}


def create_app(repo: Repo, store: ObjectStore, enqueue: Enqueue,
               authenticator: Authenticator | None = None,
               settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    if settings.auth_mode not in ("open", "dev_header"):
        raise ValueError(f"unknown auth_mode: {settings.auth_mode}")
    if authenticator is None and settings.auth_mode == "open":
        log.warning("auth disabled: open access")
    authn: Authenticator = authenticator or (auth.dev_authenticator
                                             if settings.auth_mode == "dev_header"
                                             else auth.open_authenticator)
    app = FastAPI(title="DQA", docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def trace(request: Request, call_next: Callable[..., Any]) -> Any:
        request.state.trace_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        resp = await call_next(request)
        resp.headers["X-Request-Id"] = request.state.trace_id
        return resp

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, e: ApiError) -> JSONResponse:
        return _err(request, e.status, e.code, e.message, e.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, e: RequestValidationError) -> JSONResponse:
        loc = [".".join(str(p) for p in x["loc"]) for x in e.errors()]
        return _err(request, 422, "validation_error", "Request is invalid.", {"fields": loc})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, e: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "not_found"}.get(e.status_code, "internal_error")
        return _err(request, e.status_code, code, "Not found." if code == "not_found" else "Error.")

    def principal(request: Request) -> Principal:
        p = authn(request)
        if p is None:
            raise ApiError(401, "unauthenticated", "Authentication required.")
        return p

    Who = Annotated[Principal, Depends(principal)]

    def require(p: Principal, allowed: frozenset[str]) -> None:
        if not p.has(allowed):
            raise ApiError(403, "forbidden", "Not permitted.")

    def visible_batch(p: Principal, batch_id: str) -> dict[str, Any]:
        b = repo.get_batch(batch_id)
        # Uploader sees only own batches; 404 either way so existence does not leak.
        if b is None or (p.roles == {"Uploader"} and b.get("created_by") != p.user):
            raise ApiError(404, "not_found", "Batch not found.")
        return b

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        repo.list_batches(owner=None, limit=1)  # raises -> 500 if the repo is unreachable
        return {"status": "ready"}

    @app.post("/api/v1/batches", status_code=202)
    async def upload(p: Who, file: Annotated[UploadFile, File()],
                     idempotency_key: Annotated[str | None, Header()] = None) -> dict[str, str]:
        require(p, auth.UPLOAD)
        if not idempotency_key:
            raise ApiError(422, "validation_error", "Idempotency-Key header is required.",
                           {"fields": ["header.Idempotency-Key"]})
        data = await file.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise ApiError(413, "payload_too_large", "File too large; split it and upload again.",
                           {"max_bytes": settings.max_upload_bytes})
        if data and sniff_format(data[:SNIFF_BYTES], file.filename, file.content_type) == "unknown":
            raise ApiError(422, "validation_error", "File could not be parsed as JSON or CSV.",
                           {"line": 1, "position": 0, "reason": "format_unrecognised"})
        sha = hashlib.sha256(data).hexdigest()
        bid = f"b_{uuid.uuid4().hex}"  # ponytail: uuid4, ULID (sortable) when the id scheme is fixed
        key = f"uploads/{bid}"
        bid, created = repo.create_batch(batch_id=bid, idempotency_key=idempotency_key,
                                         file_sha256=sha, created_by=p.user, object_key=key)
        if created:
            # ponytail: no outbox (LLD 3.6): a crash here strands a queued batch; sweeper re-enqueues.
            store.put(key, data)
            repo.append_audit(actor=p.user, event_type="upload", entity=bid,
                              payload={"file_sha256": sha, "size": len(data)})
            enqueue(QUEUE_INGEST, {"type": "batch_created", "batch_id": bid})
        return {"batch_id": bid, "status": "queued"}  # PROVISIONAL(OQ-17): empty file also 202

    @app.get("/api/v1/batches/{batch_id}")
    def batch_status(p: Who, batch_id: str) -> dict[str, Any]:
        require(p, auth.READ_BATCH)
        b = visible_batch(p, batch_id)
        return {
            "batch_id": b["batch_id"], "status": b["status"], "records": b.get("record_count", 0),
            "findings_by_type": repo.count_findings_by_type(batch_id),
            "ai_status": b.get("ai_status", "not_started"),
            "created_at": b.get("created_at"), "completed_at": b.get("completed_at"),
        }

    @app.get("/api/v1/batches/{batch_id}/findings")
    def findings(p: Who, batch_id: str,
                 issue_type: IssueType | None = None, severity: Severity | None = None,
                 source: Source | None = None, status: Status | None = None,
                 cursor: str | None = None,
                 limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 50) -> dict[str, Any]:
        require(p, auth.READ_FINDINGS)
        visible_batch(p, batch_id)
        items, nxt = repo.list_findings(
            batch_id, issue_type=issue_type, severity=severity, source=source, status=status,
            cursor=cursor, limit=limit)
        return {"items": [f.model_dump(mode="json") for f in items], "next_cursor": nxt}

    @app.get("/api/v1/reference-data/{type_}")
    def reference_data(p: Who, type_: str) -> dict[str, Any]:
        require(p, auth.ALL_ROLES)
        if type_ not in _REF_TYPES:
            raise ApiError(404, "not_found", "Unknown reference data type.")
        ref = Reference()  # PROVISIONAL(OQ-22): defaults only; versioned store + write path later
        return {"type": type_, "version": ref.version, "values": getattr(ref, type_)}

    return app
