"""SEAM akses data untuk resource `jabatan` (domain ANJAB).

`JabatanService` adalah kontrak (Protocol). `InMemoryJabatanService` adalah
PLACEHOLDER in-memory. Ganti dengan implementasi nyata lewat
skill `backend-postgresql-skill` — kontrak tidak berubah.
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
from ..schemas.jabatan import JabatanCreate, JabatanRead, JabatanUpdate

SEARCHABLE_FIELDS = frozenset(
    {"id", "kode", "nama", "jenis", "unit_kerja_id", "aktif", "created_at"}
)


class JabatanService(Protocol):
    """Kontrak operasi terhadap jabatan (CRUD + search)."""

    def list(self, *, limit: int, offset: int) -> tuple[list[JabatanRead], int]: ...
    def get(self, jabatan_id: str) -> JabatanRead: ...
    def create(self, data: JabatanCreate) -> JabatanRead: ...
    def update(self, jabatan_id: str, data: JabatanUpdate) -> JabatanRead: ...
    def delete(self, jabatan_id: str) -> None: ...
    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[JabatanRead], int]: ...


@dataclass
class _Record:
    id: str
    kode: str
    nama: str
    jenis: str
    aktif: bool
    created_at: datetime
    unit_kerja_id: str | None = None
    deskripsi: str | None = None


class InMemoryJabatanService:
    """Placeholder in-memory thread-safe — BUKAN sumber data nyata."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> JabatanRead:
        return JabatanRead.model_validate(rec)

    def list(self, *, limit: int, offset: int) -> tuple[list[JabatanRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: r.nama)
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, jabatan_id: str) -> JabatanRead:
        with self._lock:
            rec = self._data.get(jabatan_id)
        if rec is None:
            raise NotFoundError(f"Jabatan '{jabatan_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, data: JabatanCreate) -> JabatanRead:
        with self._lock:
            if any(r.kode == data.kode for r in self._data.values()):
                raise ConflictError(f"Jabatan dengan kode '{data.kode}' sudah ada.")
            rec = _Record(
                id=f"jbt_{uuid.uuid4().hex[:8]}",
                kode=data.kode,
                nama=data.nama,
                jenis=data.jenis,
                unit_kerja_id=data.unit_kerja_id,
                deskripsi=data.deskripsi,
                aktif=data.aktif,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, jabatan_id: str, data: JabatanUpdate) -> JabatanRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(jabatan_id)
            if rec is None:
                raise NotFoundError(f"Jabatan '{jabatan_id}' tidak ditemukan.")
            if "kode" in changes:
                if any(
                    r.kode == changes["kode"] and r.id != jabatan_id for r in self._data.values()
                ):
                    raise ConflictError(f"Jabatan dengan kode '{changes['kode']}' sudah ada.")
            for key, value in changes.items():
                setattr(rec, key, value)
            return self._to_read(rec)

    def delete(self, jabatan_id: str) -> None:
        with self._lock:
            if jabatan_id not in self._data:
                raise NotFoundError(f"Jabatan '{jabatan_id}' tidak ditemukan.")
            del self._data[jabatan_id]

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[JabatanRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        with self._lock:
            records = [asdict(r) for r in self._data.values()]
        page, total = run_search(records, domain, order, limit, offset)
        return [JabatanRead.model_validate(r) for r in page], total
