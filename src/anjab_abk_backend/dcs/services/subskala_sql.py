"""Implementasi `DcsSubSkalaService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryDcsSubSkalaService` TANPA mengubah kontrak Protocol.

Sub-skala & item adalah MASTER DATA yang di-seed terpisah (bukan tugas service
ini untuk membuat). Service ini hanya MEMBACA dan mengizinkan admin mengubah
teks/arah/urutan item lewat `update_item`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...errors import NotFoundError
from ...models import DcsItemModel, DcsSubSkalaModel
from ..schemas.subskala import (
    DcsItemRead,
    DcsItemUpdate,
    DcsSubSkalaRead,
    DcsSubSkalaWithItemsRead,
)


def _to_item_read(rec: DcsItemModel) -> DcsItemRead:
    return DcsItemRead(
        id=rec.id,
        item_id=rec.item_id,
        subskala_kode=rec.subskala_kode,
        sub_dimensi=rec.sub_dimensi,
        pernyataan=rec.pernyataan,
        arah=rec.arah,  # type: ignore[arg-type]
        urutan=rec.urutan,
    )


def _to_sub_skala_read(rec: DcsSubSkalaModel) -> DcsSubSkalaRead:
    return DcsSubSkalaRead(id=rec.id, kode=rec.kode, nama=rec.nama, urutan=rec.urutan)


class SqlDcsSubSkalaService:
    """`DcsSubSkalaService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_item_model(self, item_id: str) -> DcsItemModel:
        rec = self._s.scalar(select(DcsItemModel).where(DcsItemModel.item_id == item_id))
        if rec is None:
            raise NotFoundError(f"Item DCS '{item_id}' tidak ditemukan.")
        return rec

    def list_sub_skala(self) -> list[DcsSubSkalaRead]:
        rows = self._s.scalars(
            select(DcsSubSkalaModel).order_by(DcsSubSkalaModel.urutan.asc())
        ).all()
        return [_to_sub_skala_read(s) for s in rows]

    def get_sub_skala(self, kode: str) -> DcsSubSkalaWithItemsRead:
        rec = self._s.scalar(select(DcsSubSkalaModel).where(DcsSubSkalaModel.kode == kode))
        if rec is None:
            raise NotFoundError(f"Sub-skala DCS '{kode}' tidak ditemukan.")
        sk_read = _to_sub_skala_read(rec)
        items_rows = self._s.scalars(
            select(DcsItemModel)
            .where(DcsItemModel.subskala_kode == kode)
            .order_by(DcsItemModel.urutan.asc())
        ).all()
        items = [_to_item_read(i) for i in items_rows]
        return DcsSubSkalaWithItemsRead(**sk_read.model_dump(), items=items)

    def list_item(self) -> list[DcsItemRead]:
        rows = self._s.scalars(select(DcsItemModel).order_by(DcsItemModel.urutan.asc())).all()
        return [_to_item_read(i) for i in rows]

    def get_item_by_item_id(self, item_id: str) -> DcsItemRead:
        return _to_item_read(self._get_item_model(item_id))

    def update_item(self, item_id: str, data: DcsItemUpdate) -> DcsItemRead:
        rec = self._get_item_model(item_id)
        patch = data.model_dump(exclude_unset=True)
        if "pernyataan" in patch:
            rec.pernyataan = patch["pernyataan"]
        if "arah" in patch:
            rec.arah = patch["arah"]
        if "urutan" in patch:
            rec.urutan = patch["urutan"]
        self._s.flush()
        return _to_item_read(rec)
