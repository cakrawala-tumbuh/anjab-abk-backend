"""SEAM akses data untuk resource `jenjang_pendidikan`.

`JenjangPendidikanService` adalah kontrak (Protocol). `InMemoryJenjangPendidikanService`
adalah PLACEHOLDER in-memory. Ganti dengan implementasi nyata lewat
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
from ..schemas.jenjang_pendidikan import (
    JenjangPendidikanCreate,
    JenjangPendidikanRead,
    JenjangPendidikanUpdate,
)

SEARCHABLE_FIELDS = frozenset({"id", "kode", "nama", "urutan", "aktif"})


class JenjangPendidikanService(Protocol):
    """Kontrak operasi terhadap jenjang_pendidikan (CRUD + search)."""

    def list(self, *, limit: int, offset: int) -> tuple[list[JenjangPendidikanRead], int]: ...
    def get(self, jp_id: str) -> JenjangPendidikanRead: ...
    def create(self, data: JenjangPendidikanCreate) -> JenjangPendidikanRead: ...
    def update(self, jp_id: str, data: JenjangPendidikanUpdate) -> JenjangPendidikanRead: ...
    def delete(self, jp_id: str) -> None: ...
    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[JenjangPendidikanRead], int]: ...


@dataclass
class _Record:
    id: str
    kode: str
    nama: str
    urutan: int
    aktif: bool


class InMemoryJenjangPendidikanService:
    """Placeholder in-memory thread-safe — BUKAN sumber data nyata."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> JenjangPendidikanRead:
        return JenjangPendidikanRead.model_validate(rec)

    def list(self, *, limit: int, offset: int) -> tuple[list[JenjangPendidikanRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: (r.urutan, r.nama))
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, jp_id: str) -> JenjangPendidikanRead:
        with self._lock:
            rec = self._data.get(jp_id)
        if rec is None:
            raise NotFoundError(f"Jenjang pendidikan '{jp_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, data: JenjangPendidikanCreate) -> JenjangPendidikanRead:
        with self._lock:
            if any(r.kode == data.kode for r in self._data.values()):
                raise ConflictError(f"Jenjang dengan kode '{data.kode}' sudah ada.")
            rec = _Record(
                id=f"jp_{uuid.uuid4().hex[:8]}",
                kode=data.kode,
                nama=data.nama,
                urutan=data.urutan,
                aktif=data.aktif,
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, jp_id: str, data: JenjangPendidikanUpdate) -> JenjangPendidikanRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(jp_id)
            if rec is None:
                raise NotFoundError(f"Jenjang pendidikan '{jp_id}' tidak ditemukan.")
            if "kode" in changes:
                if any(r.kode == changes["kode"] and r.id != jp_id for r in self._data.values()):
                    raise ConflictError(f"Jenjang dengan kode '{changes['kode']}' sudah ada.")
            for key, value in changes.items():
                setattr(rec, key, value)
            return self._to_read(rec)

    def delete(self, jp_id: str) -> None:
        with self._lock:
            if jp_id not in self._data:
                raise NotFoundError(f"Jenjang pendidikan '{jp_id}' tidak ditemukan.")
            del self._data[jp_id]

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[JenjangPendidikanRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        with self._lock:
            records = [asdict(r) for r in self._data.values()]
        page, total = run_search(records, domain, order, limit, offset)
        return [JenjangPendidikanRead.model_validate(r) for r in page], total
