"""SEAM akses data untuk resource `TsLog`."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ..schemas.log import TsLogCreate, TsLogRead, TsLogUpdate


def _parse_hhmm(t: str) -> int:
    """Konversi string HH:MM ke total menit sejak tengah malam."""
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _validate_times_and_minutes(
    waktu_masuk: str,
    waktu_keluar: str,
    menit_core: int,
    menit_character: int,
    menit_improve: int,
    menit_strategic: int,
    menit_admin: int,
    menit_recovery: int,
) -> None:
    masuk = _parse_hhmm(waktu_masuk)
    keluar = _parse_hhmm(waktu_keluar)
    if masuk >= keluar:
        raise ValidationAppError("waktu_masuk harus lebih awal dari waktu_keluar.")
    total_work = keluar - masuk
    total_menit = (
        menit_core
        + menit_character
        + menit_improve
        + menit_strategic
        + menit_admin
        + menit_recovery
    )
    if total_menit > total_work + 30:
        raise ValidationAppError(
            f"Total menit aktivitas ({total_menit}) melebihi batas toleransi"
            f" (durasi kerja {total_work} menit + 30 menit)."
        )


@dataclass
class _Record:
    id: str
    responden_id: str
    tanggal: date
    waktu_masuk: str
    waktu_keluar: str
    day_color: str
    menit_core: int
    menit_character: int
    menit_improve: int
    menit_strategic: int
    menit_admin: int
    menit_recovery: int
    created_at: datetime
    updated_at: datetime
    catatan: str | None = None


class TsLogService(Protocol):
    """Kontrak operasi terhadap TsLog."""

    def list_by_responden(self, responden_id: str) -> list[TsLogRead]: ...
    def count_by_responden(self, responden_id: str) -> int: ...
    def get(self, log_id: str) -> TsLogRead: ...
    def create(self, responden_id: str, data: TsLogCreate) -> TsLogRead: ...
    def update(self, log_id: str, data: TsLogUpdate) -> TsLogRead: ...


class InMemoryTsLogService:
    """Placeholder in-memory thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    @staticmethod
    def _to_read(rec: _Record) -> TsLogRead:
        return TsLogRead.model_validate(rec)

    def list_by_responden(self, responden_id: str) -> list[TsLogRead]:
        with self._lock:
            ordered = sorted(
                (r for r in self._data.values() if r.responden_id == responden_id),
                key=lambda r: r.tanggal,
                reverse=True,
            )
        return [self._to_read(r) for r in ordered]

    def count_by_responden(self, responden_id: str) -> int:
        with self._lock:
            return sum(1 for r in self._data.values() if r.responden_id == responden_id)

    def get(self, log_id: str) -> TsLogRead:
        with self._lock:
            rec = self._data.get(log_id)
        if rec is None:
            raise NotFoundError(f"Log Time Study '{log_id}' tidak ditemukan.")
        return self._to_read(rec)

    def create(self, responden_id: str, data: TsLogCreate) -> TsLogRead:
        _validate_times_and_minutes(
            data.waktu_masuk,
            data.waktu_keluar,
            data.menit_core,
            data.menit_character,
            data.menit_improve,
            data.menit_strategic,
            data.menit_admin,
            data.menit_recovery,
        )
        with self._lock:
            already = any(
                r.responden_id == responden_id and r.tanggal == data.tanggal
                for r in self._data.values()
            )
            if already:
                raise ConflictError(
                    f"Log untuk responden '{responden_id}' tanggal '{data.tanggal}' sudah ada."
                )
            now = datetime.now(UTC)
            rec = _Record(
                id=f"tlog_{uuid.uuid4().hex[:8]}",
                responden_id=responden_id,
                tanggal=data.tanggal,
                waktu_masuk=data.waktu_masuk,
                waktu_keluar=data.waktu_keluar,
                day_color=data.day_color,
                menit_core=data.menit_core,
                menit_character=data.menit_character,
                menit_improve=data.menit_improve,
                menit_strategic=data.menit_strategic,
                menit_admin=data.menit_admin,
                menit_recovery=data.menit_recovery,
                catatan=data.catatan,
                created_at=now,
                updated_at=now,
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def update(self, log_id: str, data: TsLogUpdate) -> TsLogRead:
        changes = data.model_dump(exclude_unset=True)
        with self._lock:
            rec = self._data.get(log_id)
            if rec is None:
                raise NotFoundError(f"Log Time Study '{log_id}' tidak ditemukan.")
            # Apply changes to a temporary dict to validate
            new_waktu_masuk = changes.get("waktu_masuk", rec.waktu_masuk)
            new_waktu_keluar = changes.get("waktu_keluar", rec.waktu_keluar)
            new_menit_core = changes.get("menit_core", rec.menit_core)
            new_menit_character = changes.get("menit_character", rec.menit_character)
            new_menit_improve = changes.get("menit_improve", rec.menit_improve)
            new_menit_strategic = changes.get("menit_strategic", rec.menit_strategic)
            new_menit_admin = changes.get("menit_admin", rec.menit_admin)
            new_menit_recovery = changes.get("menit_recovery", rec.menit_recovery)
            _validate_times_and_minutes(
                new_waktu_masuk,
                new_waktu_keluar,
                new_menit_core,
                new_menit_character,
                new_menit_improve,
                new_menit_strategic,
                new_menit_admin,
                new_menit_recovery,
            )
            for key, value in changes.items():
                setattr(rec, key, value)
            rec.updated_at = datetime.now(UTC)
            return self._to_read(rec)
