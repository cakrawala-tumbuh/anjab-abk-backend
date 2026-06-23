"""Implementasi `TsRespondenService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTsRespondenService` TANPA mengubah kontrak Protocol.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError
from ...models import TsRespondenModel
from ..schemas.responden import TsRespondenCreate, TsRespondenRead


def _to_read(rec: TsRespondenModel) -> TsRespondenRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return TsRespondenRead(
        id=rec.id,
        sesi_id=rec.sesi_id,
        nama=rec.nama,
        jabatan_label=rec.jabatan_label,
        partisipan_id=rec.partisipan_id,
        created_at=created,
    )


class SqlTsRespondenService:
    """`TsRespondenService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, responden_id: str) -> TsRespondenModel:
        rec = self._s.get(TsRespondenModel, responden_id)
        if rec is None:
            raise NotFoundError(f"Responden Time Study '{responden_id}' tidak ditemukan.")
        return rec

    def list_by_sesi(self, sesi_id: str) -> list[TsRespondenRead]:
        rows = self._s.scalars(
            select(TsRespondenModel)
            .where(TsRespondenModel.sesi_id == sesi_id)
            .order_by(TsRespondenModel.created_at.asc())
        ).all()
        return [_to_read(r) for r in rows]

    def list_by_partisipan(self, partisipan_id: str) -> list[TsRespondenRead]:
        rows = self._s.scalars(
            select(TsRespondenModel)
            .where(TsRespondenModel.partisipan_id == partisipan_id)
            .order_by(TsRespondenModel.created_at.asc())
        ).all()
        return [_to_read(r) for r in rows]

    def get(self, responden_id: str) -> TsRespondenRead:
        return _to_read(self._get_model(responden_id))

    def create(self, sesi_id: str, data: TsRespondenCreate) -> TsRespondenRead:
        if data.partisipan_id is not None:
            already = self._s.scalar(
                select(TsRespondenModel.id).where(
                    TsRespondenModel.partisipan_id == data.partisipan_id,
                    TsRespondenModel.sesi_id == sesi_id,
                )
            )
            if already is not None:
                raise ConflictError(
                    f"Partisipan '{data.partisipan_id}' sudah terdaftar sebagai responden"
                    f" Time Study dalam sesi ini."
                )
        rec = TsRespondenModel(
            id=f"trsp_{uuid.uuid4().hex[:8]}",
            sesi_id=sesi_id,
            nama=data.nama,
            jabatan_label=data.jabatan_label,
            partisipan_id=data.partisipan_id,
        )
        self._s.add(rec)
        self._s.flush()
        return _to_read(rec)

    def delete(self, responden_id: str) -> None:
        rec = self._get_model(responden_id)
        self._s.delete(rec)
        self._s.flush()
