"""SEAM akses data untuk resource `OpmSesi` dan snapshot task-nya."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from ...errors import NotFoundError, ValidationAppError
from ...schemas.search import Domain, Order
from ...services.domain import run_search, validate_searchable_fields
from ..schemas.sesi import OpmSesiCreate, OpmSesiRead, OpmSesiTaskRead, OpmSesiUpdate, StatusSesi

SEARCHABLE_FIELDS = frozenset({"id", "jabatan_id", "ti_sesi_id", "periode", "status", "created_at"})

_VALID_TRANSITIONS: dict[StatusSesi, StatusSesi] = {
    "DRAFT": "OPEN",
    "OPEN": "CLOSED",
    "CLOSED": "ANALYZED",
}


@dataclass
class _Record:
    id: str
    jabatan_id: str
    ti_sesi_id: str
    periode: str
    status: str
    min_responden: int
    max_responden: int
    created_at: datetime
    catatan: str | None = None
    tasks: list[OpmSesiTaskRead] = field(default_factory=list)


class OpmSesiService(Protocol):
    """Kontrak operasi terhadap OpmSesi."""

    def list(self, *, limit: int, offset: int) -> tuple[list[OpmSesiRead], int]: ...
    def get(self, sesi_id: str) -> OpmSesiRead: ...
    def create(self, data: OpmSesiCreate) -> OpmSesiRead: ...
    def update(self, sesi_id: str, data: OpmSesiUpdate) -> OpmSesiRead: ...
    def delete(self, sesi_id: str) -> None: ...
    def transition(self, sesi_id: str, target: StatusSesi) -> OpmSesiRead: ...
    def list_task(self, sesi_id: str) -> list[OpmSesiTaskRead]: ...
    def get_task_kodes(self, sesi_id: str) -> set[str]: ...
    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[OpmSesiRead], int]: ...


class InMemoryOpmSesiService:
    """Placeholder in-memory thread-safe.

    Catatan: validasi lintas-domain (jabatan, SME panel, snapshot Task Inventory)
    dilakukan `SqlOpmSesiService.create()` — implementasi in-memory ini HANYA
    menjaga siklus hidup sesi itu sendiri (tidak dipakai produksi).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> OpmSesiRead:
        return OpmSesiRead(
            id=rec.id,
            jabatan_id=rec.jabatan_id,
            jabatan_nama=None,
            ti_sesi_id=rec.ti_sesi_id,
            periode=rec.periode,
            status=rec.status,  # type: ignore[arg-type]
            min_responden=rec.min_responden,
            max_responden=rec.max_responden,
            jumlah_task=len(rec.tasks),
            catatan=rec.catatan,
            created_at=rec.created_at,
        )

    def list(self, *, limit: int, offset: int) -> tuple[list[OpmSesiRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: r.created_at, reverse=True)
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, sesi_id: str) -> OpmSesiRead:
        with self._lock:
            rec = self._data.get(sesi_id)
        if rec is None:
            raise NotFoundError(f"Sesi OPM '{sesi_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, data: OpmSesiCreate) -> OpmSesiRead:
        if data.min_responden > data.max_responden:
            raise ValidationAppError("min_responden tidak boleh lebih besar dari max_responden.")
        with self._lock:
            rec = _Record(
                id=f"opses_{uuid.uuid4().hex[:8]}",
                jabatan_id=data.jabatan_id,
                ti_sesi_id=data.ti_sesi_id,
                periode=data.periode,
                status="DRAFT",
                min_responden=data.min_responden,
                max_responden=data.max_responden,
                catatan=data.catatan,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, sesi_id: str, data: OpmSesiUpdate) -> OpmSesiRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi OPM '{sesi_id}' tidak ditemukan.")
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
                raise NotFoundError(f"Sesi OPM '{sesi_id}' tidak ditemukan.")
            if rec.status != "DRAFT":
                raise ValidationAppError("Sesi hanya dapat dihapus saat berstatus DRAFT.")
            del self._data[sesi_id]

    def transition(self, sesi_id: str, target: StatusSesi) -> OpmSesiRead:
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi OPM '{sesi_id}' tidak ditemukan.")
            expected = _VALID_TRANSITIONS.get(rec.status)  # type: ignore[arg-type]
            if expected != target:
                raise ValidationAppError(
                    f"Transisi dari '{rec.status}' ke '{target}' tidak valid."
                    f" Transisi yang diizinkan: '{rec.status}' → '{expected}'."
                )
            rec.status = target
            return self._to_read(rec)

    def list_task(self, sesi_id: str) -> list[OpmSesiTaskRead]:
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi OPM '{sesi_id}' tidak ditemukan.")
            return list(rec.tasks)

    def get_task_kodes(self, sesi_id: str) -> set[str]:
        return {t.task_kode for t in self.list_task(sesi_id)}

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[OpmSesiRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        with self._lock:
            records = [
                {
                    "id": r.id,
                    "jabatan_id": r.jabatan_id,
                    "ti_sesi_id": r.ti_sesi_id,
                    "periode": r.periode,
                    "status": r.status,
                    "created_at": r.created_at,
                }
                for r in self._data.values()
            ]
            read_by_id = {r.id: self._to_read(r) for r in self._data.values()}
        page, total = run_search(records, domain, order, limit, offset)
        return [read_by_id[row["id"]] for row in page], total
