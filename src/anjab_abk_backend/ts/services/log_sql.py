"""Implementasi `TsLogService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTsLogService` TANPA mengubah kontrak Protocol.

Validasi waktu & menit dipakai ULANG dari `.log` (`_validate_times_and_minutes`).
Keunikan `(partisipan_id, tanggal)` ditegakkan oleh constraint DB; flush dibungkus
SAVEPOINT agar `IntegrityError` dipetakan ke `ConflictError` tanpa merusak
transaksi request.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError
from ...models import TsLogModel
from ..schemas.log import TsLogCreate, TsLogRead, TsLogUpdate

# Sumber tunggal validasi waktu & menit.
from .log import _validate_times_and_minutes


def _to_read(rec: TsLogModel) -> TsLogRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    updated = rec.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=UTC)
    return TsLogRead(
        id=rec.id,
        partisipan_id=rec.partisipan_id,
        tanggal=rec.tanggal,
        waktu_masuk=rec.waktu_masuk,
        waktu_keluar=rec.waktu_keluar,
        day_color=rec.day_color,  # type: ignore[arg-type]
        menit_core=rec.menit_core,
        menit_character=rec.menit_character,
        menit_improve=rec.menit_improve,
        menit_strategic=rec.menit_strategic,
        menit_admin=rec.menit_admin,
        menit_recovery=rec.menit_recovery,
        catatan=rec.catatan,
        created_at=created,
        updated_at=updated,
    )


class SqlTsLogService:
    """`TsLogService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, log_id: str) -> TsLogModel:
        rec = self._s.get(TsLogModel, log_id)
        if rec is None:
            raise NotFoundError(f"Log Time Study '{log_id}' tidak ditemukan.")
        return rec

    def _flush_checked(self, *, on_conflict: str) -> None:
        """Flush dalam SAVEPOINT; petakan pelanggaran keunikan ke `ConflictError`.

        SAVEPOINT (`begin_nested`) WAJIB di PostgreSQL: `IntegrityError` membatalkan
        seluruh transaksi sampai di-rollback. Dengan savepoint, rollback hanya ke
        savepoint sehingga transaksi request tetap sehat.
        """
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(on_conflict) from exc

    def list_by_partisipan(
        self, partisipan_id: str, *, limit: int | None = None, offset: int = 0
    ) -> tuple[list[TsLogRead], int]:
        total = (
            self._s.scalar(
                select(func.count())
                .select_from(TsLogModel)
                .where(TsLogModel.partisipan_id == partisipan_id)
            )
            or 0
        )
        stmt = (
            select(TsLogModel)
            .where(TsLogModel.partisipan_id == partisipan_id)
            .order_by(TsLogModel.tanggal.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        elif offset:
            stmt = stmt.offset(offset)
        rows = self._s.scalars(stmt).all()
        return [_to_read(r) for r in rows], total

    def count_by_partisipan(self, partisipan_id: str) -> int:
        return (
            self._s.scalar(
                select(func.count())
                .select_from(TsLogModel)
                .where(TsLogModel.partisipan_id == partisipan_id)
            )
            or 0
        )

    def get(self, log_id: str) -> TsLogRead:
        return _to_read(self._get_model(log_id))

    def create(self, partisipan_id: str, data: TsLogCreate) -> TsLogRead:
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
        # Pre-cek untuk pesan ramah; unique constraint tetap jadi backstop balapan.
        already = self._s.scalar(
            select(TsLogModel.id).where(
                TsLogModel.partisipan_id == partisipan_id,
                TsLogModel.tanggal == data.tanggal,
            )
        )
        if already is not None:
            raise ConflictError(
                f"Log untuk partisipan '{partisipan_id}' tanggal '{data.tanggal}' sudah ada."
            )
        now = datetime.now(UTC)
        rec = TsLogModel(
            id=f"tlog_{uuid.uuid4().hex[:8]}",
            partisipan_id=partisipan_id,
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
        self._s.add(rec)
        self._flush_checked(
            on_conflict=(
                f"Log untuk partisipan '{partisipan_id}' tanggal '{data.tanggal}' sudah ada."
            )
        )
        return _to_read(rec)

    def update(self, log_id: str, data: TsLogUpdate) -> TsLogRead:
        rec = self._get_model(log_id)
        changes = data.model_dump(exclude_unset=True)
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
        self._flush_checked(
            on_conflict=(
                f"Log untuk partisipan '{rec.partisipan_id}' tanggal"
                f" '{changes.get('tanggal', rec.tanggal)}' sudah ada."
            )
        )
        return _to_read(rec)
