"""Implementasi `TiRespondenService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTiRespondenService` TANPA mengubah kontrak Protocol.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import NotFoundError, ValidationAppError
from ...models import TiRespondenModel
from ..schemas.responden import TiRespondenCreate, TiRespondenRead


def _to_read(rec: TiRespondenModel) -> TiRespondenRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    t1 = rec.tahap1_submitted_at
    if t1 is not None and t1.tzinfo is None:
        t1 = t1.replace(tzinfo=UTC)
    t3 = rec.tahap3_submitted_at
    if t3 is not None and t3.tzinfo is None:
        t3 = t3.replace(tzinfo=UTC)
    return TiRespondenRead(
        id=rec.id,
        sesi_id=rec.sesi_id,
        nama=rec.nama,
        partisipan_id=rec.partisipan_id,
        tahap1_submit=rec.tahap1_submit,
        tahap1_submitted_at=t1,
        tahap3_submit=rec.tahap3_submit,
        tahap3_submitted_at=t3,
        created_at=created,
    )


class SqlTiRespondenService:
    """`TiRespondenService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, responden_id: str) -> TiRespondenModel:
        rec = self._s.get(TiRespondenModel, responden_id)
        if rec is None:
            raise NotFoundError(f"Responden Task Inventory '{responden_id}' tidak ditemukan.")
        return rec

    def list_by_sesi(self, sesi_id: str) -> list[TiRespondenRead]:
        rows = self._s.scalars(
            select(TiRespondenModel)
            .where(TiRespondenModel.sesi_id == sesi_id)
            .order_by(TiRespondenModel.created_at.asc())
        ).all()
        return [_to_read(r) for r in rows]

    def list_by_partisipan(self, partisipan_id: str) -> list[TiRespondenRead]:
        rows = self._s.scalars(
            select(TiRespondenModel)
            .where(TiRespondenModel.partisipan_id == partisipan_id)
            .order_by(TiRespondenModel.created_at.asc())
        ).all()
        return [_to_read(r) for r in rows]

    def count_by_sesi(self, sesi_id: str) -> int:
        return (
            self._s.scalar(
                select(func.count())
                .select_from(TiRespondenModel)
                .where(TiRespondenModel.sesi_id == sesi_id)
            )
            or 0
        )

    def count_tahap1_submitted(self, sesi_id: str) -> int:
        return (
            self._s.scalar(
                select(func.count())
                .select_from(TiRespondenModel)
                .where(
                    TiRespondenModel.sesi_id == sesi_id,
                    TiRespondenModel.tahap1_submit.is_(True),
                )
            )
            or 0
        )

    def get(self, responden_id: str) -> TiRespondenRead:
        return _to_read(self._get_model(responden_id))

    def create(self, sesi_id: str, data: TiRespondenCreate, max_responden: int) -> TiRespondenRead:
        current = self.count_by_sesi(sesi_id)
        if current >= max_responden:
            raise ValidationAppError(
                f"Sesi sudah mencapai batas maksimum {max_responden} responden."
            )
        rec = TiRespondenModel(
            id=f"trsp_{uuid.uuid4().hex[:8]}",
            sesi_id=sesi_id,
            nama=data.nama,
            partisipan_id=data.partisipan_id,
            tahap1_submit=False,
            tahap3_submit=False,
        )
        self._s.add(rec)
        self._s.flush()
        return _to_read(rec)

    def ensure_for_partisipan(
        self, sesi_id: str, *, partisipan_id: str, nama: str | None
    ) -> TiRespondenRead:
        """Idempoten: kembalikan responden untuk (sesi_id, partisipan_id) bila sudah ada,
        selain itu buat baru. Tidak menerapkan batas max_responden.
        """
        existing = self._s.scalar(
            select(TiRespondenModel)
            .where(
                TiRespondenModel.sesi_id == sesi_id,
                TiRespondenModel.partisipan_id == partisipan_id,
            )
            .order_by(TiRespondenModel.created_at.asc())
        )
        if existing is not None:
            return _to_read(existing)
        rec = TiRespondenModel(
            id=f"trsp_{uuid.uuid4().hex[:8]}",
            sesi_id=sesi_id,
            nama=nama,
            partisipan_id=partisipan_id,
            tahap1_submit=False,
            tahap3_submit=False,
        )
        self._s.add(rec)
        self._s.flush()
        return _to_read(rec)

    def mark_tahap1(self, responden_id: str) -> TiRespondenRead:
        rec = self._get_model(responden_id)
        if rec.tahap1_submit:
            raise ValidationAppError("Responden ini sudah menyelesaikan Tahap 1.")
        rec.tahap1_submit = True
        rec.tahap1_submitted_at = datetime.now(UTC)
        self._s.flush()
        return _to_read(rec)

    def mark_tahap3(self, responden_id: str) -> TiRespondenRead:
        rec = self._get_model(responden_id)
        if rec.tahap3_submit:
            raise ValidationAppError("Responden ini sudah menyelesaikan Tahap 3.")
        rec.tahap3_submit = True
        rec.tahap3_submitted_at = datetime.now(UTC)
        self._s.flush()
        return _to_read(rec)

    def delete(self, responden_id: str) -> None:
        rec = self._get_model(responden_id)
        if rec.tahap1_submit or rec.tahap3_submit:
            raise ValidationAppError("Responden yang sudah submit (Tahap 1/3) tidak dapat dihapus.")
        self._s.delete(rec)
        self._s.flush()
