"""SEAM akses data untuk resource `TsSesi`."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ...errors import NotFoundError, ValidationAppError
from ..schemas.sesi import StatusSesi, TsSesiCreate, TsSesiRead, TsSesiUpdate

_VALID_TRANSITIONS: dict[StatusSesi, StatusSesi] = {
    "DRAFT": "OPEN",
    "OPEN": "CLOSED",
    "CLOSED": "ANALYZED",
}


@dataclass
class _Record:
    id: str
    jabatan_id: str
    periode: str
    status: str
    created_at: datetime
    catatan: str | None = None


class TsSesiService(Protocol):
    """Kontrak operasi terhadap TsSesi."""

    def list(self, *, limit: int, offset: int) -> tuple[list[TsSesiRead], int]: ...
    def get(self, sesi_id: str) -> TsSesiRead: ...
    def create(self, data: TsSesiCreate) -> TsSesiRead: ...
    def update(self, sesi_id: str, data: TsSesiUpdate) -> TsSesiRead: ...
    def delete(self, sesi_id: str) -> None: ...
    def transition(self, sesi_id: str, target: StatusSesi) -> TsSesiRead: ...


class InMemoryTsSesiService:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> TsSesiRead:
        return TsSesiRead.model_validate(rec)

    def list(self, *, limit: int, offset: int) -> tuple[list[TsSesiRead], int]:
        with self._lock:
            ordered = sorted(self._data.values(), key=lambda r: r.created_at, reverse=True)
        page = ordered[offset : offset + limit]
        return [self._to_read(r) for r in page], len(ordered)

    def get(self, sesi_id: str) -> TsSesiRead:
        with self._lock:
            rec = self._data.get(sesi_id)
        if rec is None:
            raise NotFoundError(f"Sesi Time Study '{sesi_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, data: TsSesiCreate) -> TsSesiRead:
        with self._lock:
            rec = _Record(
                id=f"tses_{uuid.uuid4().hex[:8]}",
                jabatan_id=data.jabatan_id,
                periode=data.periode,
                status="DRAFT",
                catatan=data.catatan,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, sesi_id: str, data: TsSesiUpdate) -> TsSesiRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi Time Study '{sesi_id}' tidak ditemukan.")
            if rec.status != "DRAFT":
                raise ValidationAppError("Sesi hanya dapat diperbarui saat berstatus DRAFT.")
            for key, value in changes.items():
                setattr(rec, key, value)
            return self._to_read(rec)

    def delete(self, sesi_id: str) -> None:
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi Time Study '{sesi_id}' tidak ditemukan.")
            if rec.status != "DRAFT":
                raise ValidationAppError("Sesi hanya dapat dihapus saat berstatus DRAFT.")
            del self._data[sesi_id]

    def transition(self, sesi_id: str, target: StatusSesi) -> TsSesiRead:
        with self._lock:
            rec = self._data.get(sesi_id)
            if rec is None:
                raise NotFoundError(f"Sesi Time Study '{sesi_id}' tidak ditemukan.")
            expected = _VALID_TRANSITIONS.get(rec.status)  # type: ignore[arg-type]
            if expected != target:
                raise ValidationAppError(
                    f"Transisi dari '{rec.status}' ke '{target}' tidak valid."
                    f" Transisi yang diizinkan: '{rec.status}' → '{expected}'."
                )
            rec.status = target
            return self._to_read(rec)
