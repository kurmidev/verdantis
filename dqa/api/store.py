"""Object store port (S3 in prod) plus an in-memory impl for tests/dev."""
from typing import Protocol


class ObjectStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...


class MemoryStore:
    def __init__(self) -> None:
        self._d: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self._d[key] = data

    def get(self, key: str) -> bytes:
        return self._d[key]
