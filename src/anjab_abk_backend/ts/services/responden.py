"""SEAM akses data untuk resource `TsResponden`."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import ConflictError, NotFoundError
from ..schemas.responden import TsRespondenCreate, TsRespondenRead


@dataclass
class _Record:
    id: str
    sesi_id: str
    jabatan_label: str
    created_at: datetime
    nama: str | None = None
    partisipan_id: str | None = None


class TsRespondenService(Protocol):
    """Kontrak operasi terhadap TsResponden."""

    def list_by_sesi(self, sesi_id: str) -> list[TsRespondenRead]: ...
    def list_by_partisipan(self, partisipan_id: str) -> list[TsRespondenRead]: ...
    def get(self, responden_id: str) -> TsRespondenRead: ...
    def create(self, sesi_id: str, data: TsRespondenCreate) -> TsRespondenRead: ...
    def delete(self, responden_id: str) -> None: ...


class InMemoryTsRespondenService:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> TsRespondenRead:
        return TsRespondenRead.model_validate(rec)

    def list_by_sesi(self, sesi_id: str) -> list[TsRespondenRead]:
        with self._lock:
            ordered = sorted(
                (r for r in self._data.values() if r.sesi_id == sesi_id),
                key=lambda r: r.created_at,
            )
        return [self._to_read(r) for r in ordered]

    def list_by_partisipan(self, partisipan_id: str) -> list[TsRespondenRead]:
        with self._lock:
            ordered = sorted(
                (r for r in self._data.values() if r.partisipan_id == partisipan_id),
                key=lambda r: r.created_at,
            )
        return [self._to_read(r) for r in ordered]

    def get(self, responden_id: str) -> TsRespondenRead:
        with self._lock:
            rec = self._data.get(responden_id)
        if rec is None:
            raise NotFoundError(f"Responden Time Study '{responden_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, sesi_id: str, data: TsRespondenCreate) -> TsRespondenRead:
        with self._lock:
            if data.partisipan_id is not None:
                already = any(
                    r.partisipan_id == data.partisipan_id and r.sesi_id == sesi_id
                    for r in self._data.values()
                )
                if already:
                    raise ConflictError(
                        f"Partisipan '{data.partisipan_id}' sudah terdaftar sebagai responden"
                        f" Time Study dalam sesi ini."
                    )
            rec = _Record(
                id=f"trsp_{uuid.uuid4().hex[:8]}",
                sesi_id=sesi_id,
                nama=data.nama,
                jabatan_label=data.jabatan_label,
                partisipan_id=data.partisipan_id,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def delete(self, responden_id: str) -> None:
        with self._lock:
            rec = self._data.get(responden_id)
            if rec is None:
                raise NotFoundError(f"Responden Time Study '{responden_id}' tidak ditemukan.")
            del self._data[responden_id]
