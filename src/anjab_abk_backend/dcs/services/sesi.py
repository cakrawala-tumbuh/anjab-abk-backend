"""SEAM akses data untuk resource `DcsSesi`."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import NotFoundError, ValidationAppError
from ...schemas.search import Domain, Order
from ...services.domain import run_search, validate_searchable_fields
from ..schemas.sesi import DcsSesiCreate, DcsSesiRead, DcsSesiUpdate, StatusSesiDcs

SEARCHABLE_FIELDS = frozenset({"id", "periode", "status", "created_at"})

_VALID_TRANSITIONS: dict[StatusSesiDcs, StatusSesiDcs] = {
    "DRAFT": "OPEN",
    "OPEN": "CLOSED",
    "CLOSED": "ANALYZED",
}

_ERR_NON_DRAFT = (
    "Sesi hanya dapat dihapus saat berstatus DRAFT."
    " Gunakan paksa=true untuk menghapus sesi beserta SELURUH responden & jawabannya."
)


@dataclass
class _Record:
    id: str
    periode: str
    status: str
    min_responden: int
    max_responden: int
    created_at: datetime
    catatan: str | None = None


class DcsSesiService(Protocol):
    """Kontrak operasi terhadap DcsSesi."""

    def list(self, *, limit: int, offset: int) -> tuple[list[DcsSesiRead], int]: ...
    def get(self, sesi_id: str) -> DcsSesiRead: ...
    def create(self, data: DcsSesiCreate) -> DcsSesiRead: ...
    def update(self, sesi_id: str, data: DcsSesiUpdate) -> DcsSesiRead: ...
    def delete(self, sesi_id: str, *, paksa: bool = False) -> None: ...
    def transition(self, sesi_id: str, target: StatusSesiDcs) -> DcsSesiRead: ...
    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[DcsSesiRead], int]: ...


class InMemoryDcsSesiService:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> DcsSesiRead:
        return DcsSesiRead.model_validate(rec)

    def list(self, *, limit: int, offset: int) -> tuple[list[DcsSesiRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: r.created_at, reverse=True)
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, sesi_id: str) -> DcsSesiRead:
        with self._lock:
            rec = self._data.get(sesi_id)
        if rec is None:
            raise NotFoundError(f"Sesi DCS '{sesi_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, data: DcsSesiCreate) -> DcsSesiRead:
        if data.min_responden > data.max_responden:
            raise ValidationAppError("min_responden tidak boleh lebih besar dari max_responden.")
        with self._lock:
            rec = _Record(
                id=f"dses_{uuid.uuid4().hex[:8]}",
                periode=data.periode,
                status="DRAFT",
                min_responden=data.min_responden,
                max_responden=data.max_responden,
                catatan=data.catatan,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, sesi_id: str, data: DcsSesiUpdate) -> DcsSesiRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi DCS '{sesi_id}' tidak ditemukan.")
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

    def delete(self, sesi_id: str, *, paksa: bool = False) -> None:
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi DCS '{sesi_id}' tidak ditemukan.")
            if rec.status != "DRAFT" and not paksa:
                raise ValidationAppError(_ERR_NON_DRAFT)
            del self._data[sesi_id]

    def transition(self, sesi_id: str, target: StatusSesiDcs) -> DcsSesiRead:
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi DCS '{sesi_id}' tidak ditemukan.")
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
    ) -> tuple[list[DcsSesiRead], int]:
        from dataclasses import asdict

        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        with self._lock:
            records = [asdict(r) for r in self._data.values()]
        page, total = run_search(records, domain, order, limit, offset)
        return [DcsSesiRead.model_validate(r) for r in page], total
