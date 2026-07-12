"""SEAM akses data untuk resource `TsPenugasan`."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import ConflictError, NotFoundError
from ...schemas.common import BulkAssignResult
from ..schemas.penugasan import TsPenugasanCreate, TsPenugasanRead, TsPenugasanUpdate


@dataclass
class _Record:
    id: str
    partisipan_id: str
    created_at: datetime
    aktif: bool = True
    catatan: str | None = None


class TsPenugasanService(Protocol):
    """Kontrak operasi terhadap TsPenugasan."""

    def list(self, *, limit: int, offset: int) -> tuple[list[TsPenugasanRead], int]: ...
    def get(self, penugasan_id: str) -> TsPenugasanRead: ...
    def get_by_partisipan(self, partisipan_id: str) -> TsPenugasanRead | None: ...
    def create(self, data: TsPenugasanCreate) -> TsPenugasanRead: ...
    def create_banyak(
        self, partisipan_ids: list[str], *, aktif: bool, catatan: str | None
    ) -> BulkAssignResult[TsPenugasanRead]: ...
    def update(self, penugasan_id: str, data: TsPenugasanUpdate) -> TsPenugasanRead: ...
    def delete(self, penugasan_id: str) -> None: ...


class InMemoryTsPenugasanService:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> TsPenugasanRead:
        return TsPenugasanRead.model_validate(rec)

    def list(self, *, limit: int, offset: int) -> tuple[list[TsPenugasanRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: r.created_at, reverse=True)
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, penugasan_id: str) -> TsPenugasanRead:
        with self._lock:
            rec = self._data.get(penugasan_id)
        if rec is None:
            raise NotFoundError(f"Penugasan Time Study '{penugasan_id}' tidak ditemukan.")
        return self._to_read(rec)

    def get_by_partisipan(self, partisipan_id: str) -> TsPenugasanRead | None:
        with self._lock:
            rec = next((r for r in self._data.values() if r.partisipan_id == partisipan_id), None)
        return self._to_read(rec) if rec is not None else None

    def create(self, data: TsPenugasanCreate) -> TsPenugasanRead:
        with self._lock:
            already = any(r.partisipan_id == data.partisipan_id for r in self._data.values())
            if already:
                raise ConflictError(
                    f"Partisipan '{data.partisipan_id}' sudah memiliki penugasan Time Study."
                )
            rec = _Record(
                id=f"tpn_{uuid.uuid4().hex[:8]}",
                partisipan_id=data.partisipan_id,
                aktif=data.aktif,
                catatan=data.catatan,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, penugasan_id: str, data: TsPenugasanUpdate) -> TsPenugasanRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(penugasan_id)
            if rec is None:
                raise NotFoundError(f"Penugasan Time Study '{penugasan_id}' tidak ditemukan.")
            for key, value in changes.items():
                setattr(rec, key, value)
            return self._to_read(rec)

    def delete(self, penugasan_id: str) -> None:
        with self._lock:
            rec = self._data.get(penugasan_id)
            if rec is None:
                raise NotFoundError(f"Penugasan Time Study '{penugasan_id}' tidak ditemukan.")
            del self._data[penugasan_id]
