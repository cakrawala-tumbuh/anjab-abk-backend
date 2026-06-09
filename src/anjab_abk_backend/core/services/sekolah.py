"""SEAM akses data untuk resource `sekolah`.

`SekolahService` adalah kontrak (Protocol). `InMemorySekolahService` adalah
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
from ..schemas.sekolah import SekolahCreate, SekolahRead, SekolahUpdate

SEARCHABLE_FIELDS = frozenset(
    {"id", "nama", "npsn", "jenjang_pendidikan_id", "kota", "provinsi", "aktif", "created_at"}
)


class SekolahService(Protocol):
    """Kontrak operasi terhadap sekolah (CRUD + search)."""

    def list(self, *, limit: int, offset: int) -> tuple[list[SekolahRead], int]: ...
    def get(self, sekolah_id: str) -> SekolahRead: ...
    def create(self, data: SekolahCreate) -> SekolahRead: ...
    def update(self, sekolah_id: str, data: SekolahUpdate) -> SekolahRead: ...
    def delete(self, sekolah_id: str) -> None: ...
    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[SekolahRead], int]: ...


@dataclass
class _Record:
    id: str
    nama: str
    jenjang_pendidikan_id: str
    created_at: datetime
    npsn: str | None = None
    kota: str | None = None
    provinsi: str | None = None
    aktif: bool = True


class InMemorySekolahService:
    """Placeholder in-memory thread-safe — BUKAN sumber data nyata."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> SekolahRead:
        return SekolahRead.model_validate(rec)

    def list(self, *, limit: int, offset: int) -> tuple[list[SekolahRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: r.nama)
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, sekolah_id: str) -> SekolahRead:
        with self._lock:
            rec = self._data.get(sekolah_id)
        if rec is None:
            raise NotFoundError(f"Sekolah '{sekolah_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, data: SekolahCreate) -> SekolahRead:
        with self._lock:
            if data.npsn and any(r.npsn == data.npsn for r in self._data.values()):
                raise ConflictError(f"Sekolah dengan NPSN '{data.npsn}' sudah ada.")
            rec = _Record(
                id=f"skl_{uuid.uuid4().hex[:8]}",
                nama=data.nama,
                npsn=data.npsn,
                jenjang_pendidikan_id=data.jenjang_pendidikan_id,
                kota=data.kota,
                provinsi=data.provinsi,
                aktif=data.aktif,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, sekolah_id: str, data: SekolahUpdate) -> SekolahRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(sekolah_id)
            if rec is None:
                raise NotFoundError(f"Sekolah '{sekolah_id}' tidak ditemukan.")
            if "npsn" in changes and changes["npsn"]:
                if any(
                    r.npsn == changes["npsn"] and r.id != sekolah_id for r in self._data.values()
                ):
                    raise ConflictError(f"Sekolah dengan NPSN '{changes['npsn']}' sudah ada.")
            for key, value in changes.items():
                setattr(rec, key, value)
            return self._to_read(rec)

    def delete(self, sekolah_id: str) -> None:
        with self._lock:
            if sekolah_id not in self._data:
                raise NotFoundError(f"Sekolah '{sekolah_id}' tidak ditemukan.")
            del self._data[sekolah_id]

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[SekolahRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        with self._lock:
            records = [asdict(r) for r in self._data.values()]
        page, total = run_search(records, domain, order, limit, offset)
        return [SekolahRead.model_validate(r) for r in page], total
