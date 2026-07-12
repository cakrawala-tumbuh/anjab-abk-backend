"""SEAM akses data untuk resource `UraianTugas` (master data catalog TI).

`UraianTugasService` adalah kontrak (Protocol). `InMemoryUraianTugasService` adalah
PLACEHOLDER in-memory yang di-seed dari task_catalog.json.
Ganti dengan implementasi PostgreSQL lewat skill `backend-postgresql-skill` — kontrak tidak berubah.

UraianTugas punya relasi M2O ke TugasPokok (tugas_pokok_id), M2O ke DetilTugas
(detil_tugas_id, opsional), dan M2O ke Jabatan (jabatan_id, langsung tersimpan).
Jabatan yang dipilih harus ada dalam jabatan_ids DetilTugas induk (bila detil_tugas_id diisi).
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...schemas.search import Domain, Order
from ...services.domain import run_search, validate_searchable_fields
from ..schemas.uraian_tugas import UraianTugasCreate, UraianTugasRead, UraianTugasUpdate

if TYPE_CHECKING:
    from .detil_tugas import InMemoryDetilTugasService

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
    jabatan_id: str
    urutan: int
    tugas_pokok_id: str
    created_at: datetime
    detil_tugas_id: str | None = None
    std_sumber_bukti: str | None = None
    std_kondisi: str | None = None
    std_frekuensi_teks: str | None = None
    std_durasi_per_kali: str | None = None
    std_jam_per_minggu: float | None = None
    std_peak4w_hours: float | None = None
    std_ai_mode: str | None = None
    std_va_type: str | None = None
    std_dcs_flag: bool | None = None


class InMemoryUraianTugasService:
    """Placeholder in-memory thread-safe — BUKAN sumber data nyata."""

    def __init__(self, dt_svc: InMemoryDetilTugasService | None = None) -> None:
        self._dt = dt_svc
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    def _validate_jabatan_in_dt(self, jabatan_id: str, detil_tugas_id: str) -> None:
        if self._dt is None:
            return
        try:
            dt = self._dt.get(detil_tugas_id)
        except NotFoundError:
            raise NotFoundError(f"DetilTugas '{detil_tugas_id}' tidak ditemukan.") from None
        if jabatan_id not in dt.jabatan_ids:
            raise ValidationAppError(
                f"Jabatan '{jabatan_id}' bukan bagian dari jabatan_ids"
                f" DetilTugas '{detil_tugas_id}'."
            )

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
        if data.detil_tugas_id:
            self._validate_jabatan_in_dt(data.jabatan_id, data.detil_tugas_id)
        with self._lock:
            if any(r.kode == data.kode for r in self._data.values()):
                raise ConflictError(f"UraianTugas dengan kode '{data.kode}' sudah ada.")
            rec = _Record(
                id=f"ut_{uuid.uuid4().hex[:8]}",
                kode=data.kode,
                uraian=data.uraian,
                unit=data.unit,
                jabatan_id=data.jabatan_id,
                urutan=data.urutan,
                detil_tugas_id=data.detil_tugas_id,
                tugas_pokok_id=data.tugas_pokok_id,
                created_at=datetime.now(UTC),
                std_sumber_bukti=data.std_sumber_bukti,
                std_kondisi=data.std_kondisi,
                std_frekuensi_teks=data.std_frekuensi_teks,
                std_durasi_per_kali=data.std_durasi_per_kali,
                std_jam_per_minggu=data.std_jam_per_minggu,
                std_peak4w_hours=data.std_peak4w_hours,
                std_ai_mode=data.std_ai_mode,
                std_va_type=data.std_va_type,
                std_dcs_flag=data.std_dcs_flag,
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
            new_jabatan_id = changes.get("jabatan_id", rec.jabatan_id)
            new_detil_id = changes.get("detil_tugas_id", rec.detil_tugas_id)
        # Validasi jabatan di luar lock
        if new_detil_id and ("jabatan_id" in changes or "detil_tugas_id" in changes):
            self._validate_jabatan_in_dt(new_jabatan_id, new_detil_id)
        with self._lock:
            rec = self._data.get(ut_id)
            if rec is None:
                raise NotFoundError(f"UraianTugas '{ut_id}' tidak ditemukan.")
            for key, value in changes.items():
                setattr(rec, key, value)
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
