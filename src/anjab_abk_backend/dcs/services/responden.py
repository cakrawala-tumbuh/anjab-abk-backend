"""SEAM akses data untuk resource `DcsResponden`."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import NotFoundError, ValidationAppError
from ..schemas.responden import DcsRespondenCreate, DcsRespondenRead


@dataclass
class _Record:
    id: str
    sesi_id: str
    jabatan_label: str
    sudah_submit: bool
    created_at: datetime
    nama: str | None = None
    partisipan_id: str | None = None
    submitted_at: datetime | None = None


class DcsRespondenService(Protocol):
    """Kontrak operasi terhadap DcsResponden."""

    def list_by_sesi(self, sesi_id: str) -> list[DcsRespondenRead]: ...
    def list_by_partisipan(self, partisipan_id: str) -> list[DcsRespondenRead]: ...
    def get(self, responden_id: str) -> DcsRespondenRead: ...
    def create(
        self, sesi_id: str, data: DcsRespondenCreate, max_responden: int
    ) -> DcsRespondenRead: ...
    def ensure_for_partisipan(
        self, sesi_id: str, *, partisipan_id: str, nama: str | None, jabatan_label: str
    ) -> DcsRespondenRead: ...
    def mark_submitted(self, responden_id: str) -> DcsRespondenRead: ...
    def delete(self, responden_id: str) -> None: ...


class InMemoryDcsRespondenService:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> DcsRespondenRead:
        return DcsRespondenRead.model_validate(rec)

    def list_by_sesi(self, sesi_id: str) -> list[DcsRespondenRead]:
        with self._lock:
            ordered = sorted(
                (r for r in self._data.values() if r.sesi_id == sesi_id),
                key=lambda r: r.created_at,
            )
        return [self._to_read(r) for r in ordered]

    def list_by_partisipan(self, partisipan_id: str) -> list[DcsRespondenRead]:
        with self._lock:
            ordered = sorted(
                (r for r in self._data.values() if r.partisipan_id == partisipan_id),
                key=lambda r: r.created_at,
            )
        return [self._to_read(r) for r in ordered]

    def count_by_sesi(self, sesi_id: str) -> int:
        with self._lock:
            return sum(1 for r in self._data.values() if r.sesi_id == sesi_id)

    def get(self, responden_id: str) -> DcsRespondenRead:
        with self._lock:
            rec = self._data.get(responden_id)
        if rec is None:
            raise NotFoundError(f"Responden DCS '{responden_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(
        self, sesi_id: str, data: DcsRespondenCreate, max_responden: int
    ) -> DcsRespondenRead:
        with self._lock:
            current_count = sum(1 for r in self._data.values() if r.sesi_id == sesi_id)
            if current_count >= max_responden:
                raise ValidationAppError(
                    f"Sesi sudah mencapai batas maksimum {max_responden} responden."
                )
            rec = _Record(
                id=f"drsp_{uuid.uuid4().hex[:8]}",
                sesi_id=sesi_id,
                nama=data.nama,
                jabatan_label=data.jabatan_label,
                partisipan_id=data.partisipan_id,
                sudah_submit=False,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def ensure_for_partisipan(
        self, sesi_id: str, *, partisipan_id: str, nama: str | None, jabatan_label: str
    ) -> DcsRespondenRead:
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
                id=f"drsp_{uuid.uuid4().hex[:8]}",
                sesi_id=sesi_id,
                nama=nama,
                jabatan_label=jabatan_label,
                partisipan_id=partisipan_id,
                sudah_submit=False,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
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
