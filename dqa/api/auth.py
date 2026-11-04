"""Authentication/authorisation (LLD 04 3.2). Real OIDC/JWT validation is P4: plug an Authenticator in."""
from dataclasses import dataclass
from typing import Protocol

from fastapi import Request

ROLES = frozenset({"Uploader", "Data Steward", "Data Owner", "Auditor", "Platform Admin"})
UPLOAD = frozenset({"Uploader", "Data Steward", "Data Owner"})
READ_FINDINGS = frozenset({"Uploader", "Data Steward", "Data Owner", "Auditor"})
# PROVISIONAL(OQ-405): "metadata only" read for Platform Admin = batch status, no findings.
READ_BATCH = READ_FINDINGS | {"Platform Admin"}
ALL_ROLES = ROLES


@dataclass(frozen=True)
class Principal:
    user: str
    roles: frozenset[str]

    def has(self, allowed: frozenset[str]) -> bool:
        return bool(self.roles & allowed)


class Authenticator(Protocol):
    def __call__(self, request: Request) -> Principal | None: ...


# ADR-023: open access, no sign-in. Everyone is 'anonymous' with every role except Platform Admin.
ANONYMOUS = Principal("anonymous", ROLES - {"Platform Admin"})


def open_authenticator(request: Request) -> Principal | None:
    return ANONYMOUS


def dev_authenticator(request: Request) -> Principal | None:
    """Test/dev only: trusts headers. Enabled by settings.auth_mode == "dev_header" (role-matrix tests)."""
    user = request.headers.get("X-Dev-User")
    roles = frozenset(r.strip() for r in request.headers.get("X-Dev-Roles", "").split(",")) & ROLES
    return Principal(user, roles) if user and roles else None
