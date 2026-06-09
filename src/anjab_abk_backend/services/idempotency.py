"""SEAM idempotency untuk request yang mengubah state."""

from __future__ import annotations

import threading
from typing import Any, Protocol


class IdempotencyStore(Protocol):
    def get(self, key: str) -> dict[str, Any] | None: ...
    def reserve(self, key: str) -> bool: ...
    def save(self, key: str, value: dict[str, Any]) -> None: ...
    def release(self, key: str) -> None: ...


class InMemoryIdempotencyStore:
    """Placeholder in-memory — BUKAN penyimpanan nyata."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._results: dict[str, dict[str, Any]] = {}
        self._in_progress: set[str] = set()

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            return self._results.get(key)

    def reserve(self, key: str) -> bool:
        with self._lock:
            if key in self._results or key in self._in_progress:
                return False
            self._in_progress.add(key)
            return True

    def save(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._results[key] = value
            self._in_progress.discard(key)

    def release(self, key: str) -> None:
        with self._lock:
            self._in_progress.discard(key)
