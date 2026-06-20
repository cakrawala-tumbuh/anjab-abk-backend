"""SEAM akses data untuk resource `partisipan`.

`PartisipanService` adalah kontrak (Protocol). `InMemoryPartisipanService` adalah
PLACEHOLDER in-memory. Ganti dengan implementasi nyata lewat
skill `backend-postgresql-skill` — kontrak tidak berubah.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from ...errors import NotFoundError
from ...schemas.search import Domain, Order
from ...services.domain import run_search, validate_searchable_fields
from ..schemas.partisipan import PartisipanCreate, PartisipanRead, PartisipanUpdate

SEARCHABLE_FIELDS = frozenset(
    {
        "id",
        "nama",
        "email",
        "sekolah_id",
        "jabatan_utama_id",
        "masa_kerja_tahun",
        "masa_kerja_bulan",
        "mata_pelajaran_utama_id",
        "aktif",
        "created_at",
    }
)


class PartisipanService(Protocol):
    """Kontrak operasi terhadap partisipan (CRUD + search)."""

    def list(self, *, limit: int, offset: int) -> tuple[list[PartisipanRead], int]: ...
    def get(self, partisipan_id: str) -> PartisipanRead: ...
    def create(
        self, data: PartisipanCreate, *, authentik_user_id: str | None = None
    ) -> PartisipanRead: ...
    def update(self, partisipan_id: str, data: PartisipanUpdate) -> PartisipanRead: ...
    def delete(self, partisipan_id: str) -> None: ...
    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[PartisipanRead], int]: ...


@dataclass
class _Record:
    id: str
    nama: str
    email: str
    sekolah_id: str
    jabatan_utama_id: str
    masa_kerja_tahun: int
    aktif: bool
    created_at: datetime
    jabatan_tambahan_ids: list[str] = field(default_factory=list)
    masa_kerja_bulan: int = 0
    mata_pelajaran_utama_id: str | None = None
    authentik_user_id: str | None = None


class InMemoryPartisipanService:
    """Placeholder in-memory thread-safe — BUKAN sumber data nyata."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> PartisipanRead:
        return PartisipanRead.model_validate(asdict(rec))

    def list(self, *, limit: int, offset: int) -> tuple[list[PartisipanRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: r.nama)
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, partisipan_id: str) -> PartisipanRead:
        with self._lock:
            rec = self._data.get(partisipan_id)
        if rec is None:
            raise NotFoundError(f"Partisipan '{partisipan_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(
        self, data: PartisipanCreate, *, authentik_user_id: str | None = None
    ) -> PartisipanRead:
        with self._lock:
            rec = _Record(
                id=f"par_{uuid.uuid4().hex[:8]}",
                nama=data.nama,
                email=data.email,
                sekolah_id=data.sekolah_id,
                jabatan_utama_id=data.jabatan_utama_id,
                jabatan_tambahan_ids=list(data.jabatan_tambahan_ids),
                masa_kerja_tahun=data.masa_kerja_tahun,
                masa_kerja_bulan=data.masa_kerja_bulan,
                mata_pelajaran_utama_id=data.mata_pelajaran_utama_id,
                aktif=data.aktif,
                created_at=datetime.now(UTC),
                authentik_user_id=authentik_user_id,
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, partisipan_id: str, data: PartisipanUpdate) -> PartisipanRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(partisipan_id)
            if rec is None:
                raise NotFoundError(f"Partisipan '{partisipan_id}' tidak ditemukan.")
            for key, value in changes.items():
                setattr(rec, key, value)
            return self._to_read(rec)

    def delete(self, partisipan_id: str) -> None:
        with self._lock:
            if partisipan_id not in self._data:
                raise NotFoundError(f"Partisipan '{partisipan_id}' tidak ditemukan.")
            del self._data[partisipan_id]

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[PartisipanRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        with self._lock:
            records = [asdict(r) for r in self._data.values()]
        page, total = run_search(records, domain, order, limit, offset)
        return [PartisipanRead.model_validate(r) for r in page], total
