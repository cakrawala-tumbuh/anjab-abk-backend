"""SEAM akses data untuk resource `TiResponden`."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import NotFoundError, ValidationAppError
from ..schemas.responden import TiRespondenCreate, TiRespondenRead


@dataclass
class _Record:
    id: str
    sesi_id: str
    tahap1_submit: bool
    tahap2_submit: bool
    created_at: datetime
    nama: str | None = None
    partisipan_id: str | None = None
    tahap1_submitted_at: datetime | None = None
    tahap2_submitted_at: datetime | None = None


class TiRespondenService(Protocol):
    """Kontrak operasi terhadap TiResponden."""

    def list_by_sesi(self, sesi_id: str) -> list[TiRespondenRead]: ...
    def list_by_partisipan(self, partisipan_id: str) -> list[TiRespondenRead]: ...
    def count_by_sesi(self, sesi_id: str) -> int: ...
    def count_tahap1_submitted(self, sesi_id: str) -> int: ...
    def get(self, responden_id: str) -> TiRespondenRead: ...
    def create(
        self, sesi_id: str, data: TiRespondenCreate, max_responden: int
    ) -> TiRespondenRead: ...
    def ensure_for_partisipan(
        self, sesi_id: str, *, partisipan_id: str, nama: str | None
    ) -> TiRespondenRead: ...
    def mark_tahap1(self, responden_id: str) -> TiRespondenRead: ...
    def mark_tahap2(self, responden_id: str) -> TiRespondenRead: ...
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

    def create(self, sesi_id: str, data: TiRespondenCreate, max_responden: int) -> TiRespondenRead:
        with self._lock:
            current = sum(1 for r in self._data.values() if r.sesi_id == sesi_id)
            if current >= max_responden:
                raise ValidationAppError(
                    f"Sesi sudah mencapai batas maksimum {max_responden} responden."
                )
            rec = _Record(
                id=f"trsp_{uuid.uuid4().hex[:8]}",
                sesi_id=sesi_id,
                nama=data.nama,
                partisipan_id=data.partisipan_id,
                tahap1_submit=False,
                tahap2_submit=False,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def ensure_for_partisipan(
        self, sesi_id: str, *, partisipan_id: str, nama: str | None
    ) -> TiRespondenRead:
        """Idempoten: kembalikan responden untuk (sesi_id, partisipan_id) bila sudah
        ada, selain itu buat baru.

        Dipakai enrollment otomatis 'Kuesioner Saya' — TIDAK menerapkan batas
        ``max_responden`` karena setiap partisipan dijamin mengisi alat ukur ini.
        """
        with self._lock:
            for r in self._data.values():
                if r.sesi_id == sesi_id and r.partisipan_id == partisipan_id:
                    return self._to_read(r)
            rec = _Record(
                id=f"trsp_{uuid.uuid4().hex[:8]}",
                sesi_id=sesi_id,
                nama=nama,
                partisipan_id=partisipan_id,
                tahap1_submit=False,
                tahap2_submit=False,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

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

    def mark_tahap2(self, responden_id: str) -> TiRespondenRead:
        with self._lock:
            rec = self._data.get(responden_id)
            if rec is None:
                raise NotFoundError(f"Responden Task Inventory '{responden_id}' tidak ditemukan.")
            if rec.tahap2_submit:
                raise ValidationAppError("Responden ini sudah menyelesaikan Tahap 2.")
            rec.tahap2_submit = True
            rec.tahap2_submitted_at = datetime.now(UTC)
            return self._to_read(rec)

    def delete(self, responden_id: str) -> None:
        with self._lock:
            rec = self._data.get(responden_id)
            if rec is None:
                raise NotFoundError(f"Responden Task Inventory '{responden_id}' tidak ditemukan.")
            if rec.tahap1_submit or rec.tahap2_submit:
                raise ValidationAppError(
                    "Responden yang sudah submit (Tahap 1/2) tidak dapat dihapus."
                )
            del self._data[responden_id]
