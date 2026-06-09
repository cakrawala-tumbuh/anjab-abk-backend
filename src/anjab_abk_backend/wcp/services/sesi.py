"""SEAM akses data untuk resource `WcpSesi`."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...schemas.search import Domain, Order
from ...services.domain import run_search, validate_searchable_fields
from ..schemas.sesi import StatusSesi, WcpSesiCreate, WcpSesiRead, WcpSesiUpdate

SEARCHABLE_FIELDS = frozenset({"id", "jabatan_id", "periode", "status", "created_at"})

_VALID_TRANSITIONS: dict[StatusSesi, StatusSesi] = {
    "DRAFT": "OPEN",
    "OPEN": "CLOSED",
    "CLOSED": "ANALYZED",
}


@dataclass
class _Record:
    id: str
    jabatan_id: str
    periode: str
    status: str
    min_responden: int
    max_responden: int
    created_at: datetime
    catatan: str | None = None


class WcpSesiService(Protocol):
    """Kontrak operasi terhadap WcpSesi."""

    def list(self, *, limit: int, offset: int) -> tuple[list[WcpSesiRead], int]: ...
    def get(self, sesi_id: str) -> WcpSesiRead: ...
    def create(self, data: WcpSesiCreate) -> WcpSesiRead: ...
    def update(self, sesi_id: str, data: WcpSesiUpdate) -> WcpSesiRead: ...
    def delete(self, sesi_id: str) -> None: ...
    def transition(self, sesi_id: str, target: StatusSesi) -> WcpSesiRead: ...
    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[WcpSesiRead], int]: ...


class InMemoryWcpSesiService:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> WcpSesiRead:
        return WcpSesiRead.model_validate(rec)

    def list(self, *, limit: int, offset: int) -> tuple[list[WcpSesiRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: r.created_at, reverse=True)
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, sesi_id: str) -> WcpSesiRead:
        with self._lock:
            rec = self._data.get(sesi_id)
        if rec is None:
            raise NotFoundError(f"Sesi WCP '{sesi_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, data: WcpSesiCreate) -> WcpSesiRead:
        if data.min_responden > data.max_responden:
            raise ValidationAppError("min_responden tidak boleh lebih besar dari max_responden.")
        with self._lock:
            if any(
                r.jabatan_id == data.jabatan_id and r.periode == data.periode
                for r in self._data.values()
            ):
                raise ConflictError(
                    f"Sesi WCP untuk jabatan '{data.jabatan_id}'"
                    f" periode '{data.periode}' sudah ada."
                )
            rec = _Record(
                id=f"wses_{uuid.uuid4().hex[:8]}",
                jabatan_id=data.jabatan_id,
                periode=data.periode,
                status="DRAFT",
                min_responden=data.min_responden,
                max_responden=data.max_responden,
                catatan=data.catatan,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, sesi_id: str, data: WcpSesiUpdate) -> WcpSesiRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi WCP '{sesi_id}' tidak ditemukan.")
            if rec.status != "DRAFT":
                raise ValidationAppError("Sesi hanya dapat diperbarui saat berstatus DRAFT.")
            new_min = changes.get("min_responden", rec.min_responden)
            new_max = changes.get("max_responden", rec.max_responden)
            if new_min > new_max:
                raise ValidationAppError(
                    "min_responden tidak boleh lebih besar dari max_responden."
                )
            for key, value in changes.items():
                setattr(rec, key, value)
            return self._to_read(rec)

    def delete(self, sesi_id: str) -> None:
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi WCP '{sesi_id}' tidak ditemukan.")
            if rec.status != "DRAFT":
                raise ValidationAppError("Sesi hanya dapat dihapus saat berstatus DRAFT.")
            del self._data[sesi_id]

    def transition(self, sesi_id: str, target: StatusSesi) -> WcpSesiRead:
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi WCP '{sesi_id}' tidak ditemukan.")
            expected = _VALID_TRANSITIONS.get(rec.status)  # type: ignore[arg-type]
            if expected != target:
                raise ValidationAppError(
                    f"Transisi dari '{rec.status}' ke '{target}' tidak valid."
                    f" Transisi yang diizinkan: '{rec.status}' → '{expected}'."
                )
            rec.status = target
            return self._to_read(rec)

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[WcpSesiRead], int]:
        from dataclasses import asdict

        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        with self._lock:
            records = [asdict(r) for r in self._data.values()]
        page, total = run_search(records, domain, order, limit, offset)
        return [WcpSesiRead.model_validate(r) for r in page], total
