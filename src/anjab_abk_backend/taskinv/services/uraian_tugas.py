"""SEAM akses data untuk resource `UraianTugas` (master data catalog TI).

`UraianTugasService` adalah kontrak (Protocol). `InMemoryUraianTugasService` adalah
PLACEHOLDER in-memory yang di-seed dari task_catalog.json.
Ganti dengan implementasi PostgreSQL lewat skill `backend-postgresql-skill` — kontrak tidak berubah.

UraianTugas punya relasi M2O ke TugasPokok (tugas_pokok_id) dan DetilTugas (detil_tugas_id).
jabatan_id DIWARISKAN dari TugasPokok dan di-denormalisasi ke internal record untuk
efisiensi query filter (diganti JOIN di PostgreSQL).
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from ...errors import ConflictError, NotFoundError
from ...schemas.search import Domain, Order
from ...services.domain import run_search, validate_searchable_fields
from ..schemas.uraian_tugas import UraianTugasCreate, UraianTugasRead, UraianTugasUpdate

if TYPE_CHECKING:
    from .tugas_pokok import InMemoryTugasPokokService

SEARCHABLE_FIELDS = frozenset(
    {
        "id",
        "kode",
        "uraian",
        "unit",
        "jabatan_id",
        "urutan",
        "detil_tugas_id",
        "tugas_pokok_id",
        "created_at",
    }
)


class UraianTugasService(Protocol):
    """Kontrak operasi terhadap UraianTugas (CRUD + search)."""

    def list(self, *, limit: int, offset: int) -> tuple[list[UraianTugasRead], int]: ...
    def get(self, ut_id: str) -> UraianTugasRead: ...
    def get_by_kode(self, kode: str) -> UraianTugasRead: ...
    def create(self, data: UraianTugasCreate) -> UraianTugasRead: ...
    def update(self, ut_id: str, data: UraianTugasUpdate) -> UraianTugasRead: ...
    def delete(self, ut_id: str) -> None: ...
    def list_by_unit_jabatan(self, unit: str, jabatan_id: str) -> list[UraianTugasRead]: ...
    def list_by_jabatan(self, jabatan_id: str) -> list[UraianTugasRead]: ...
    def list_by_detil_tugas(self, dt_id: str) -> list[UraianTugasRead]: ...
    def list_by_tugas_pokok(self, tp_id: str) -> list[UraianTugasRead]: ...
    def valid_kodes(self, unit: str, jabatan_id: str) -> set[str]: ...
    def valid_kodes_for_jabatan(self, jabatan_id: str) -> set[str]: ...
    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[UraianTugasRead], int]: ...


@dataclass
class _Record:
    id: str
    kode: str
    uraian: str
    unit: str
    jabatan_id: str  # denormalisasi dari TugasPokok untuk efisiensi filter
    urutan: int
    tugas_pokok_id: str
    created_at: datetime
    detil_tugas_id: str | None = None


class InMemoryUraianTugasService:
    """Placeholder in-memory thread-safe — BUKAN sumber data nyata.

    Menerima `tp_svc` untuk resolve jabatan_id saat create (denormalisasi).
    """

    def __init__(self, tp_svc: InMemoryTugasPokokService) -> None:
        self._tp = tp_svc
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    def _resolve_jabatan_id(self, tugas_pokok_id: str) -> str:
        try:
            tp = self._tp.get(tugas_pokok_id)
            return tp.jabatan_id
        except NotFoundError:
            return ""

    def _to_read(self, rec: _Record) -> UraianTugasRead:
        return UraianTugasRead.model_validate(rec)

    def list(self, *, limit: int, offset: int) -> tuple[list[UraianTugasRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: (r.jabatan_id, r.unit, r.urutan))
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, ut_id: str) -> UraianTugasRead:
        with self._lock:
            rec = self._data.get(ut_id)
        if rec is None:
            raise NotFoundError(f"UraianTugas '{ut_id}' tidak ditemukan.")
        return self._to_read(rec)

    def get_by_kode(self, kode: str) -> UraianTugasRead:
        with self._lock:
            for rec in self._data.values():
                if rec.kode == kode:
                    return self._to_read(rec)
        raise NotFoundError(f"UraianTugas dengan kode '{kode}' tidak ditemukan.")

    def create(self, data: UraianTugasCreate) -> UraianTugasRead:
        jabatan_id = self._resolve_jabatan_id(data.tugas_pokok_id)
        with self._lock:
            if any(r.kode == data.kode for r in self._data.values()):
                raise ConflictError(f"UraianTugas dengan kode '{data.kode}' sudah ada.")
            rec = _Record(
                id=f"ut_{uuid.uuid4().hex[:8]}",
                kode=data.kode,
                uraian=data.uraian,
                unit=data.unit,
                jabatan_id=jabatan_id,
                urutan=data.urutan,
                detil_tugas_id=data.detil_tugas_id,
                tugas_pokok_id=data.tugas_pokok_id,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, ut_id: str, data: UraianTugasUpdate) -> UraianTugasRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(ut_id)
            if rec is None:
                raise NotFoundError(f"UraianTugas '{ut_id}' tidak ditemukan.")
            if "kode" in changes:
                if any(r.kode == changes["kode"] and r.id != ut_id for r in self._data.values()):
                    raise ConflictError(f"UraianTugas dengan kode '{changes['kode']}' sudah ada.")
            for key, value in changes.items():
                setattr(rec, key, value)
            # Re-resolve jabatan_id bila tugas_pokok_id berubah
            if "tugas_pokok_id" in changes:
                rec.jabatan_id = self._resolve_jabatan_id(rec.tugas_pokok_id)
            return self._to_read(rec)

    def delete(self, ut_id: str) -> None:
        with self._lock:
            if ut_id not in self._data:
                raise NotFoundError(f"UraianTugas '{ut_id}' tidak ditemukan.")
            del self._data[ut_id]

    def list_by_unit_jabatan(self, unit: str, jabatan_id: str) -> list[UraianTugasRead]:
        with self._lock:
            records = [
                r for r in self._data.values() if r.unit == unit and r.jabatan_id == jabatan_id
            ]
        records.sort(key=lambda r: r.urutan)
        return [self._to_read(r) for r in records]

    def list_by_jabatan(self, jabatan_id: str) -> list[UraianTugasRead]:
        with self._lock:
            records = [r for r in self._data.values() if r.jabatan_id == jabatan_id]
        records.sort(key=lambda r: (r.unit, r.urutan))
        return [self._to_read(r) for r in records]

    def list_by_detil_tugas(self, dt_id: str) -> list[UraianTugasRead]:
        with self._lock:
            records = [r for r in self._data.values() if r.detil_tugas_id == dt_id]
        records.sort(key=lambda r: (r.unit, r.urutan))
        return [self._to_read(r) for r in records]

    def list_by_tugas_pokok(self, tp_id: str) -> list[UraianTugasRead]:
        with self._lock:
            records = [r for r in self._data.values() if r.tugas_pokok_id == tp_id]
        records.sort(key=lambda r: (r.unit, r.urutan))
        return [self._to_read(r) for r in records]

    def valid_kodes(self, unit: str, jabatan_id: str) -> set[str]:
        with self._lock:
            return {
                r.kode for r in self._data.values() if r.unit == unit and r.jabatan_id == jabatan_id
            }

    def valid_kodes_for_jabatan(self, jabatan_id: str) -> set[str]:
        with self._lock:
            return {r.kode for r in self._data.values() if r.jabatan_id == jabatan_id}

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[UraianTugasRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        with self._lock:
            records = [asdict(r) for r in self._data.values()]
        page, total = run_search(records, domain, order, limit, offset)
        return [UraianTugasRead.model_validate(r) for r in page], total
