"""SEAM akses data untuk resource `sme_panel` (domain ANJAB).

`SMEPanelService` adalah kontrak (Protocol). `InMemorySMEPanelService` adalah
PLACEHOLDER in-memory. Ganti dengan implementasi nyata lewat
skill `backend-postgresql-skill` — kontrak tidak berubah.
"""

from __future__ import annotations

import dataclasses
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Protocol

from ...errors import ConflictError, NotFoundError
from ...schemas.search import Domain, Order
from ...services.domain import run_search, validate_searchable_fields
from ..schemas.sme_panel import SMEPanelCreate, SMEPanelRead, SMEPanelUpdate

SEARCHABLE_FIELDS = frozenset({"id", "jabatan_id", "aktif", "created_at"})


class SMEPanelService(Protocol):
    """Kontrak operasi terhadap sme_panel (CRUD + anggota + search)."""

    def list(self, *, limit: int, offset: int) -> tuple[list[SMEPanelRead], int]: ...
    def get(self, panel_id: str) -> SMEPanelRead: ...
    def create(self, data: SMEPanelCreate) -> SMEPanelRead: ...
    def update(self, panel_id: str, data: SMEPanelUpdate) -> SMEPanelRead: ...
    def delete(self, panel_id: str) -> None: ...
    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[SMEPanelRead], int]: ...
    def add_anggota(self, panel_id: str, partisipan_id: str) -> SMEPanelRead: ...
    def remove_anggota(self, panel_id: str, partisipan_id: str) -> SMEPanelRead: ...


@dataclass
class _Record:
    id: str
    jabatan_id: str
    aktif: bool
    created_at: datetime
    partisipan_ids: list[str] = field(default_factory=list)


class InMemorySMEPanelService:
    """Placeholder in-memory thread-safe — BUKAN sumber data nyata."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> SMEPanelRead:
        return SMEPanelRead(
            id=rec.id,
            jabatan_id=rec.jabatan_id,
            partisipan_ids=list(rec.partisipan_ids),
            aktif=rec.aktif,
            created_at=rec.created_at,
        )

    def list(self, *, limit: int, offset: int) -> tuple[list[SMEPanelRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: r.created_at)
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, panel_id: str) -> SMEPanelRead:
        with self._lock:
            rec = self._data.get(panel_id)
        if rec is None:
            raise NotFoundError(f"SME panel '{panel_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, data: SMEPanelCreate) -> SMEPanelRead:
        with self._lock:
            if any(r.jabatan_id == data.jabatan_id for r in self._data.values()):
                raise ConflictError(f"SME panel untuk jabatan '{data.jabatan_id}' sudah ada.")
            rec = _Record(
                id=f"sme_{uuid.uuid4().hex[:8]}",
                jabatan_id=data.jabatan_id,
                aktif=data.aktif,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, panel_id: str, data: SMEPanelUpdate) -> SMEPanelRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(panel_id)
            if rec is None:
                raise NotFoundError(f"SME panel '{panel_id}' tidak ditemukan.")
            for key, value in changes.items():
                setattr(rec, key, value)
            return self._to_read(rec)

    def delete(self, panel_id: str) -> None:
        with self._lock:
            if panel_id not in self._data:
                raise NotFoundError(f"SME panel '{panel_id}' tidak ditemukan.")
            del self._data[panel_id]

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[SMEPanelRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        with self._lock:
            records = [dataclasses.asdict(r) for r in self._data.values()]
        page, total = run_search(records, domain, order, limit, offset)
        return [SMEPanelRead.model_validate(r) for r in page], total

    def add_anggota(self, panel_id: str, partisipan_id: str) -> SMEPanelRead:
        with self._lock:
            rec = self._data.get(panel_id)
            if rec is None:
                raise NotFoundError(f"SME panel '{panel_id}' tidak ditemukan.")
            if partisipan_id in rec.partisipan_ids:
                raise ConflictError(
                    f"Partisipan '{partisipan_id}' sudah menjadi anggota panel ini."
                )
            rec.partisipan_ids.append(partisipan_id)
            return self._to_read(rec)

    def remove_anggota(self, panel_id: str, partisipan_id: str) -> SMEPanelRead:
        with self._lock:
            rec = self._data.get(panel_id)
            if rec is None:
                raise NotFoundError(f"SME panel '{panel_id}' tidak ditemukan.")
            if partisipan_id not in rec.partisipan_ids:
                raise NotFoundError(f"Partisipan '{partisipan_id}' bukan anggota panel ini.")
            rec.partisipan_ids.remove(partisipan_id)
            return self._to_read(rec)
