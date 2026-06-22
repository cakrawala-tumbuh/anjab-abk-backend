"""SEAM akses data untuk resource `DetilTugas` (master data catalog TI).

`DetilTugasService` adalah kontrak (Protocol). `InMemoryDetilTugasService` adalah
PLACEHOLDER in-memory yang di-seed dari task_catalog.json.
Ganti dengan implementasi PostgreSQL lewat skill `backend-postgresql-skill` — kontrak tidak berubah.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import NotFoundError
from ...schemas.search import Domain, Order
from ...services.domain import run_search, validate_searchable_fields
from ..schemas.detil_tugas import DetilTugasCreate, DetilTugasRead, DetilTugasUpdate

SEARCHABLE_FIELDS = frozenset({"id", "nama", "tugas_pokok_id", "created_at"})


class DetilTugasService(Protocol):
    """Kontrak operasi terhadap DetilTugas (CRUD + search)."""

    def list(self, *, limit: int, offset: int) -> tuple[list[DetilTugasRead], int]: ...
    def get(self, dt_id: str) -> DetilTugasRead: ...
    def create(self, data: DetilTugasCreate) -> DetilTugasRead: ...
    def update(self, dt_id: str, data: DetilTugasUpdate) -> DetilTugasRead: ...
    def delete(self, dt_id: str) -> None: ...
    def list_by_tugas_pokok(self, tp_id: str) -> list[DetilTugasRead]: ...
    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[DetilTugasRead], int]: ...


@dataclass
class _Record:
    id: str
    nama: str
    tugas_pokok_id: str
    created_at: datetime


class InMemoryDetilTugasService:
    """Placeholder in-memory thread-safe — BUKAN sumber data nyata."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> DetilTugasRead:
        return DetilTugasRead.model_validate(rec)

    def list(self, *, limit: int, offset: int) -> tuple[list[DetilTugasRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: (r.tugas_pokok_id, r.nama))
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, dt_id: str) -> DetilTugasRead:
        with self._lock:
            rec = self._data.get(dt_id)
        if rec is None:
            raise NotFoundError(f"DetilTugas '{dt_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, data: DetilTugasCreate) -> DetilTugasRead:
        with self._lock:
            rec = _Record(
                id=f"dt_{uuid.uuid4().hex[:8]}",
                nama=data.nama,
                tugas_pokok_id=data.tugas_pokok_id,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, dt_id: str, data: DetilTugasUpdate) -> DetilTugasRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(dt_id)
            if rec is None:
                raise NotFoundError(f"DetilTugas '{dt_id}' tidak ditemukan.")
            for key, value in changes.items():
                setattr(rec, key, value)
            return self._to_read(rec)

    def delete(self, dt_id: str) -> None:
        with self._lock:
            if dt_id not in self._data:
                raise NotFoundError(f"DetilTugas '{dt_id}' tidak ditemukan.")
            del self._data[dt_id]

    def list_by_tugas_pokok(self, tp_id: str) -> list[DetilTugasRead]:
        with self._lock:
            records = [r for r in self._data.values() if r.tugas_pokok_id == tp_id]
        records.sort(key=lambda r: r.nama)
        return [self._to_read(r) for r in records]

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[DetilTugasRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        with self._lock:
            records = [asdict(r) for r in self._data.values()]
        page, total = run_search(records, domain, order, limit, offset)
        return [DetilTugasRead.model_validate(r) for r in page], total
