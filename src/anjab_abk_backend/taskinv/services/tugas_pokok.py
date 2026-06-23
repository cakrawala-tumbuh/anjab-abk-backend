"""SEAM akses data untuk resource `TugasPokok` (master data catalog TI).

`TugasPokokService` adalah kontrak (Protocol). `InMemoryTugasPokokService` adalah
PLACEHOLDER in-memory yang di-seed dari task_catalog.json.
Ganti dengan implementasi PostgreSQL lewat skill `backend-postgresql-skill` — kontrak tidak berubah.

Setiap TugasPokok memiliki relasi M2M ke Jabatan via jabatan_ids.
Nama TugasPokok bersifat unik secara global.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import ConflictError, NotFoundError
from ...schemas.search import Domain, Order
from ...services.domain import run_search, validate_searchable_fields
from ..schemas.tugas_pokok import TugasPokokCreate, TugasPokokRead, TugasPokokUpdate

SEARCHABLE_FIELDS = frozenset({"id", "nama", "created_at"})


class TugasPokokService(Protocol):
    """Kontrak operasi terhadap TugasPokok (CRUD + search)."""

    def list(self, *, limit: int, offset: int) -> tuple[list[TugasPokokRead], int]: ...
    def get(self, tp_id: str) -> TugasPokokRead: ...
    def create(self, data: TugasPokokCreate) -> TugasPokokRead: ...
    def update(self, tp_id: str, data: TugasPokokUpdate) -> TugasPokokRead: ...
    def delete(self, tp_id: str) -> None: ...
    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[TugasPokokRead], int]: ...


@dataclass
class _Record:
    id: str
    jabatan_ids: list[str]
    nama: str
    created_at: datetime

    def __post_init__(self) -> None:
        # Pastikan jabatan_ids tidak di-share antar instance
        self.jabatan_ids = list(self.jabatan_ids)


class InMemoryTugasPokokService:
    """Placeholder in-memory thread-safe — BUKAN sumber data nyata."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> TugasPokokRead:
        return TugasPokokRead.model_validate(asdict(rec))

    def list(self, *, limit: int, offset: int) -> tuple[list[TugasPokokRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: r.nama)
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, tp_id: str) -> TugasPokokRead:
        with self._lock:
            rec = self._data.get(tp_id)
        if rec is None:
            raise NotFoundError(f"TugasPokok '{tp_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, data: TugasPokokCreate) -> TugasPokokRead:
        with self._lock:
            if any(r.nama == data.nama for r in self._data.values()):
                raise ConflictError(f"TugasPokok dengan nama '{data.nama}' sudah ada.")
            rec = _Record(
                id=f"tp_{uuid.uuid4().hex[:8]}",
                jabatan_ids=list(data.jabatan_ids),
                nama=data.nama,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, tp_id: str, data: TugasPokokUpdate) -> TugasPokokRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(tp_id)
            if rec is None:
                raise NotFoundError(f"TugasPokok '{tp_id}' tidak ditemukan.")
            new_nama = changes.get("nama", rec.nama)
            if new_nama != rec.nama and any(
                r.nama == new_nama and r.id != tp_id for r in self._data.values()
            ):
                raise ConflictError(f"TugasPokok dengan nama '{new_nama}' sudah ada.")
            for key, value in changes.items():
                if key == "jabatan_ids":
                    rec.jabatan_ids = list(value)
                else:
                    setattr(rec, key, value)
            return self._to_read(rec)

    def delete(self, tp_id: str) -> None:
        with self._lock:
            if tp_id not in self._data:
                raise NotFoundError(f"TugasPokok '{tp_id}' tidak ditemukan.")
            del self._data[tp_id]

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[TugasPokokRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        with self._lock:
            records = [asdict(r) for r in self._data.values()]
        page, total = run_search(records, domain, order, limit, offset)
        return [TugasPokokRead.model_validate(r) for r in page], total
