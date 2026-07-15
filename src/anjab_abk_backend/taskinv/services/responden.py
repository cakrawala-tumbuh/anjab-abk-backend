"""SEAM akses data untuk resource `TiResponden`."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import NotFoundError, ValidationAppError
from ...schemas.common import BulkAssignResult, BulkSkipped
from ..schemas.responden import TiRespondenCreate, TiRespondenRead


@dataclass
class _Record:
    id: str
    sesi_id: str
    tahap1_submit: bool
    tahap3_submit: bool
    created_at: datetime
    nama: str | None = None
    partisipan_id: str | None = None
    tahap1_submitted_at: datetime | None = None
    tahap3_submitted_at: datetime | None = None


class TiRespondenService(Protocol):
    """Kontrak operasi terhadap TiResponden."""

    def list_by_sesi(self, sesi_id: str) -> list[TiRespondenRead]: ...
    def list_by_partisipan(self, partisipan_id: str) -> list[TiRespondenRead]: ...
    def count_by_sesi(self, sesi_id: str) -> int: ...
    def count_tahap1_submitted(self, sesi_id: str) -> int: ...
    def get(self, responden_id: str) -> TiRespondenRead: ...
    def create(self, sesi_id: str, data: TiRespondenCreate) -> TiRespondenRead: ...
    def assign_banyak(
        self, sesi_id: str, partisipan_ids: list[str]
    ) -> BulkAssignResult[TiRespondenRead]: ...
    def mark_tahap1(self, responden_id: str) -> TiRespondenRead: ...
    def mark_tahap3(self, responden_id: str) -> TiRespondenRead: ...
    def delete(self, responden_id: str) -> None: ...


class InMemoryTiRespondenService:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> TiRespondenRead:
        return TiRespondenRead.model_validate(rec)

    def list_by_sesi(self, sesi_id: str) -> list[TiRespondenRead]:
        with self._lock:
            ordered = sorted(
                (r for r in self._data.values() if r.sesi_id == sesi_id),
                key=lambda r: r.created_at,
            )
        return [self._to_read(r) for r in ordered]

    def list_by_partisipan(self, partisipan_id: str) -> list[TiRespondenRead]:
        with self._lock:
            ordered = sorted(
                (r for r in self._data.values() if r.partisipan_id == partisipan_id),
                key=lambda r: r.created_at,
            )
        return [self._to_read(r) for r in ordered]

    def count_by_sesi(self, sesi_id: str) -> int:
        with self._lock:
            return sum(1 for r in self._data.values() if r.sesi_id == sesi_id)

    def count_tahap1_submitted(self, sesi_id: str) -> int:
        with self._lock:
            return sum(1 for r in self._data.values() if r.sesi_id == sesi_id and r.tahap1_submit)

    def get(self, responden_id: str) -> TiRespondenRead:
        with self._lock:
            rec = self._data.get(responden_id)
        if rec is None:
            raise NotFoundError(f"Responden Task Inventory '{responden_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, sesi_id: str, data: TiRespondenCreate) -> TiRespondenRead:
        with self._lock:
            rec = _Record(
                id=f"trsp_{uuid.uuid4().hex[:8]}",
                sesi_id=sesi_id,
                nama=data.nama,
                partisipan_id=data.partisipan_id,
                tahap1_submit=False,
                tahap3_submit=False,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def assign_banyak(
        self, sesi_id: str, partisipan_ids: list[str]
    ) -> BulkAssignResult[TiRespondenRead]:
        """Delegasi ke `create()`/dedup lokal — TIDAK memvalidasi keanggotaan SME
        panel (sama seperti `SqlTiRespondenService`, pemanggil yang menyaring).
        """
        skipped: list[BulkSkipped] = []
        created: list[TiRespondenRead] = []
        seen: set[str] = set()
        with self._lock:
            for partisipan_id in partisipan_ids:
                if partisipan_id in seen:
                    skipped.append(
                        BulkSkipped(partisipan_id=partisipan_id, alasan="duplikat_input")
                    )
                    continue
                seen.add(partisipan_id)
                already = any(
                    r.sesi_id == sesi_id and r.partisipan_id == partisipan_id
                    for r in self._data.values()
                )
                if already:
                    skipped.append(
                        BulkSkipped(partisipan_id=partisipan_id, alasan="sudah_terdaftar")
                    )
                    continue
                rec = _Record(
                    id=f"trsp_{uuid.uuid4().hex[:8]}",
                    sesi_id=sesi_id,
                    nama=None,
                    partisipan_id=partisipan_id,
                    tahap1_submit=False,
                    tahap3_submit=False,
                    created_at=datetime.now(UTC),
                )
                self._data[rec.id] = rec
                created.append(self._to_read(rec))
        return BulkAssignResult(created=created, skipped=skipped)

    def mark_tahap1(self, responden_id: str) -> TiRespondenRead:
        with self._lock:
            rec = self._data.get(responden_id)
            if rec is None:
                raise NotFoundError(f"Responden Task Inventory '{responden_id}' tidak ditemukan.")
            if rec.tahap1_submit:
                raise ValidationAppError("Responden ini sudah menyelesaikan Tahap 1.")
            rec.tahap1_submit = True
            rec.tahap1_submitted_at = datetime.now(UTC)
            return self._to_read(rec)

    def mark_tahap3(self, responden_id: str) -> TiRespondenRead:
        with self._lock:
            rec = self._data.get(responden_id)
            if rec is None:
                raise NotFoundError(f"Responden Task Inventory '{responden_id}' tidak ditemukan.")
            if rec.tahap3_submit:
                raise ValidationAppError("Responden ini sudah menyelesaikan Tahap 3.")
            rec.tahap3_submit = True
            rec.tahap3_submitted_at = datetime.now(UTC)
            return self._to_read(rec)

    def delete(self, responden_id: str) -> None:
        with self._lock:
            rec = self._data.get(responden_id)
            if rec is None:
                raise NotFoundError(f"Responden Task Inventory '{responden_id}' tidak ditemukan.")
            if rec.tahap1_submit or rec.tahap3_submit:
                raise ValidationAppError(
                    "Responden yang sudah submit (Tahap 1/3) tidak dapat dihapus."
                )
            del self._data[responden_id]
