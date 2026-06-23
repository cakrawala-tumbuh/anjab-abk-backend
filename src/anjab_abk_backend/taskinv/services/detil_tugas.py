"""SEAM akses data untuk resource `DetilTugas` (master data catalog TI).

`DetilTugasService` adalah kontrak (Protocol). `InMemoryDetilTugasService` adalah
PLACEHOLDER in-memory yang di-seed dari task_catalog.json.
Ganti dengan implementasi PostgreSQL lewat skill `backend-postgresql-skill` — kontrak tidak berubah.

DetilTugas memiliki relasi M2M ke Jabatan via jabatan_ids. Jabatan yang dapat
dipilih harus merupakan subset dari jabatan_ids TugasPokok induknya.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from ...errors import NotFoundError, ValidationAppError
from ...schemas.search import Domain, Order
from ...services.domain import run_search, validate_searchable_fields
from ..schemas.detil_tugas import DetilTugasCreate, DetilTugasRead, DetilTugasUpdate

if TYPE_CHECKING:
    from .tugas_pokok import InMemoryTugasPokokService

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
    jabatan_ids: list[str]
    created_at: datetime

    def __post_init__(self) -> None:
        self.jabatan_ids = list(self.jabatan_ids)


class InMemoryDetilTugasService:
    """Placeholder in-memory thread-safe — BUKAN sumber data nyata."""

    def __init__(self, tp_svc: InMemoryTugasPokokService | None = None) -> None:
        self._tp = tp_svc
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    def _validate_jabatan_subset(self, jabatan_ids: list[str], tugas_pokok_id: str) -> None:
        if self._tp is None:
            return
        try:
            tp = self._tp.get(tugas_pokok_id)
        except NotFoundError:
            raise NotFoundError(f"TugasPokok '{tugas_pokok_id}' tidak ditemukan.") from None
        invalid = [jid for jid in jabatan_ids if jid not in tp.jabatan_ids]
        if invalid:
            raise ValidationAppError(
                f"Jabatan {invalid} bukan bagian dari jabatan_ids TugasPokok '{tugas_pokok_id}'."
            )

    @staticmethod
    def _to_read(rec: _Record) -> DetilTugasRead:
        return DetilTugasRead.model_validate(asdict(rec))

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
        self._validate_jabatan_subset(data.jabatan_ids, data.tugas_pokok_id)
        with self._lock:
            rec = _Record(
                id=f"dt_{uuid.uuid4().hex[:8]}",
                nama=data.nama,
                tugas_pokok_id=data.tugas_pokok_id,
                jabatan_ids=list(data.jabatan_ids),
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
            new_tp_id = changes.get("tugas_pokok_id", rec.tugas_pokok_id)
            new_jabatan_ids = changes.get("jabatan_ids", rec.jabatan_ids)
        # Validasi di luar lock untuk menghindari deadlock
        if "jabatan_ids" in changes or "tugas_pokok_id" in changes:
            self._validate_jabatan_subset(new_jabatan_ids, new_tp_id)
        with self._lock:
            rec = self._data.get(dt_id)
            if rec is None:
                raise NotFoundError(f"DetilTugas '{dt_id}' tidak ditemukan.")
            for key, value in changes.items():
                if key == "jabatan_ids":
                    rec.jabatan_ids = list(value)
                else:
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
