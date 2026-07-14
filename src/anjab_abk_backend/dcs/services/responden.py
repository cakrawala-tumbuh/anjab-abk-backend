"""SEAM akses data untuk resource `DcsResponden` (penugasan langsung ke instrumen singleton)."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...schemas.common import BulkAssignResult
from ..schemas.responden import DcsRespondenRead


@dataclass
class _Record:
    id: str
    jabatan_label: str
    sudah_submit: bool
    created_at: datetime
    nama: str | None = None
    partisipan_id: str | None = None
    submitted_at: datetime | None = None


class DcsRespondenService(Protocol):
    """Kontrak operasi terhadap DcsResponden."""

    def list_all(self) -> list[DcsRespondenRead]: ...
    def list_by_partisipan(self, partisipan_id: str) -> list[DcsRespondenRead]: ...
    def get(self, responden_id: str) -> DcsRespondenRead: ...
    def create(
        self, partisipan_id: str, nama: str | None, jabatan_label: str
    ) -> DcsRespondenRead: ...
    def create_banyak(self, partisipan_ids: list[str]) -> BulkAssignResult[DcsRespondenRead]: ...
    def mark_submitted(self, responden_id: str) -> DcsRespondenRead: ...
    def delete(self, responden_id: str) -> None: ...


class InMemoryDcsRespondenService:
    """Placeholder in-memory thread-safe.

    Tidak punya akses ke `PartisipanService`/instrumen (murni scaffold Protocol) —
    dan tidak mengimplementasikan `create_banyak` (pola yang sama dengan
    `InMemoryTsPenugasanService`/`InMemoryOpmRespondenService`: bulk assign butuh
    akses lintas-domain yang tidak dimiliki placeholder ini). Implementasi nyata
    ada di `SqlDcsRespondenService`.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> DcsRespondenRead:
        return DcsRespondenRead.model_validate(rec)

    def list_all(self) -> list[DcsRespondenRead]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: r.created_at)
        return [self._to_read(r) for r in ordered]

    def list_by_partisipan(self, partisipan_id: str) -> list[DcsRespondenRead]:
        with self._lock:
            ordered = sorted(
                (r for r in self._data.values() if r.partisipan_id == partisipan_id),
                key=lambda r: r.created_at,
            )
        return [self._to_read(r) for r in ordered]

    def get(self, responden_id: str) -> DcsRespondenRead:
        with self._lock:
            rec = self._data.get(responden_id)
        if rec is None:
            raise NotFoundError(f"Responden DCS '{responden_id}' tidak ditemukan.")
        return self._to_read(rec)

    def _insert(self, partisipan_id: str, nama: str | None, jabatan_label: str) -> _Record:
        already = any(r.partisipan_id == partisipan_id for r in self._data.values())
        if already:
            raise ConflictError(
                f"Partisipan '{partisipan_id}' sudah terdaftar sebagai responden DCS."
            )
        rec = _Record(
            id=f"drsp_{uuid.uuid4().hex[:8]}",
            nama=nama,
            jabatan_label=jabatan_label,
            partisipan_id=partisipan_id,
            sudah_submit=False,
            created_at=datetime.now(UTC),
        )
        self._data[rec.id] = rec
        return rec

    def create(self, partisipan_id: str, nama: str | None, jabatan_label: str) -> DcsRespondenRead:
        with self._lock:
            rec = self._insert(partisipan_id, nama, jabatan_label)
            return self._to_read(rec)

    def mark_submitted(self, responden_id: str) -> DcsRespondenRead:
        with self._lock:
            rec = self._data.get(responden_id)
            if rec is None:
                raise NotFoundError(f"Responden DCS '{responden_id}' tidak ditemukan.")
            if rec.sudah_submit:
                raise ValidationAppError("Responden ini sudah pernah mengirimkan jawaban.")
            rec.sudah_submit = True
            rec.submitted_at = datetime.now(UTC)
            return self._to_read(rec)

    def delete(self, responden_id: str) -> None:
        with self._lock:
            rec = self._data.get(responden_id)
            if rec is None:
                raise NotFoundError(f"Responden DCS '{responden_id}' tidak ditemukan.")
            if rec.sudah_submit:
                raise ValidationAppError("Responden yang sudah submit tidak dapat dihapus.")
            del self._data[responden_id]
