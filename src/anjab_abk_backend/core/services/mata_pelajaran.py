"""SEAM akses data untuk resource `mata_pelajaran`.

`MataPelajaranService` adalah kontrak (Protocol). `InMemoryMataPelajaranService` adalah
PLACEHOLDER in-memory. Ganti dengan implementasi nyata lewat
skill `backend-postgresql-skill` — kontrak tidak berubah.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass
from typing import Protocol

from ...errors import ConflictError, NotFoundError
from ...schemas.search import Domain, Order
from ...services.domain import run_search, validate_searchable_fields
from ..schemas.mata_pelajaran import MataPelajaranCreate, MataPelajaranRead, MataPelajaranUpdate

SEARCHABLE_FIELDS = frozenset({"id", "kode", "nama", "kelompok", "aktif"})


class MataPelajaranService(Protocol):
    """Kontrak operasi terhadap mata_pelajaran (CRUD + search)."""

    def list(self, *, limit: int, offset: int) -> tuple[list[MataPelajaranRead], int]: ...
    def get(self, mp_id: str) -> MataPelajaranRead: ...
    def create(self, data: MataPelajaranCreate) -> MataPelajaranRead: ...
    def update(self, mp_id: str, data: MataPelajaranUpdate) -> MataPelajaranRead: ...
    def delete(self, mp_id: str) -> None: ...
    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[MataPelajaranRead], int]: ...


@dataclass
class _Record:
    id: str
    kode: str
    nama: str
    kelompok: str
    aktif: bool
    deskripsi: str | None = None


class InMemoryMataPelajaranService:
    """Placeholder in-memory thread-safe — BUKAN sumber data nyata."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> MataPelajaranRead:
        return MataPelajaranRead.model_validate(rec)

    def list(self, *, limit: int, offset: int) -> tuple[list[MataPelajaranRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: r.nama)
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, mp_id: str) -> MataPelajaranRead:
        with self._lock:
            rec = self._data.get(mp_id)
        if rec is None:
            raise NotFoundError(f"Mata pelajaran '{mp_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, data: MataPelajaranCreate) -> MataPelajaranRead:
        with self._lock:
            if any(r.kode == data.kode for r in self._data.values()):
                raise ConflictError(f"Mata pelajaran dengan kode '{data.kode}' sudah ada.")
            rec = _Record(
                id=f"mp_{uuid.uuid4().hex[:8]}",
                kode=data.kode,
                nama=data.nama,
                kelompok=data.kelompok,
                deskripsi=data.deskripsi,
                aktif=data.aktif,
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, mp_id: str, data: MataPelajaranUpdate) -> MataPelajaranRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(mp_id)
            if rec is None:
                raise NotFoundError(f"Mata pelajaran '{mp_id}' tidak ditemukan.")
            if "kode" in changes:
                if any(r.kode == changes["kode"] and r.id != mp_id for r in self._data.values()):
                    raise ConflictError(
                        f"Mata pelajaran dengan kode '{changes['kode']}' sudah ada."
                    )
            for key, value in changes.items():
                setattr(rec, key, value)
            return self._to_read(rec)

    def delete(self, mp_id: str) -> None:
        with self._lock:
            if mp_id not in self._data:
                raise NotFoundError(f"Mata pelajaran '{mp_id}' tidak ditemukan.")
            del self._data[mp_id]

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[MataPelajaranRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        with self._lock:
            records = [asdict(r) for r in self._data.values()]
        page, total = run_search(records, domain, order, limit, offset)
        return [MataPelajaranRead.model_validate(r) for r in page], total
