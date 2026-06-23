"""Implementasi `WcpDimensiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryWcpDimensiService` TANPA mengubah kontrak Protocol — signature
method identik, sehingga router, skema, error envelope, dan test kontrak HTTP
tidak ikut berubah.

Master data (dimensi & item) di-SEED terpisah ke tabel `wcp_dimensi` / `wcp_item`
(ID prefix `wdim_`+kode dan `witm_`+item_id). Service ini hanya membaca master
data tersebut; hanya `update_item` yang menulis (field teks/tipe/urutan).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...errors import NotFoundError
from ...models import WcpDimensiModel, WcpItemModel
from ..schemas.dimensi import (
    WcpDimensiRead,
    WcpDimensiWithItemsRead,
    WcpItemRead,
    WcpItemUpdate,
)


def _to_item_read(rec: WcpItemModel) -> WcpItemRead:
    return WcpItemRead(
        id=rec.id,
        item_id=rec.item_id,
        dimensi_kode=rec.dimensi_kode,
        indikator_kode=rec.indikator_kode,
        indikator_label=rec.indikator_label,
        pernyataan=rec.pernyataan,
        reverse_type=rec.reverse_type,
        urutan=rec.urutan,
    )


def _to_dimensi_read(rec: WcpDimensiModel) -> WcpDimensiRead:
    return WcpDimensiRead(
        id=rec.id,
        kode=rec.kode,
        nama=rec.nama,
        urutan=rec.urutan,
        is_risk=rec.is_risk,
    )


class SqlWcpDimensiService:
    """`WcpDimensiService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def list_dimensi(self) -> list[WcpDimensiRead]:
        rows = self._s.scalars(select(WcpDimensiModel).order_by(WcpDimensiModel.urutan)).all()
        return [_to_dimensi_read(d) for d in rows]

    def get_dimensi(self, kode: str) -> WcpDimensiWithItemsRead:
        rec = self._s.scalar(select(WcpDimensiModel).where(WcpDimensiModel.kode == kode))
        if rec is None:
            raise NotFoundError(f"Dimensi WCP '{kode}' tidak ditemukan.")
        dim_read = _to_dimensi_read(rec)
        item_rows = self._s.scalars(
            select(WcpItemModel)
            .where(WcpItemModel.dimensi_kode == kode)
            .order_by(WcpItemModel.urutan)
        ).all()
        items = [_to_item_read(i) for i in item_rows]
        return WcpDimensiWithItemsRead(**dim_read.model_dump(), items=items)

    def list_item(self) -> list[WcpItemRead]:
        rows = self._s.scalars(select(WcpItemModel).order_by(WcpItemModel.urutan)).all()
        return [_to_item_read(i) for i in rows]

    def get_item_by_item_id(self, item_id: str) -> WcpItemRead:
        rec = self._s.scalar(select(WcpItemModel).where(WcpItemModel.item_id == item_id))
        if rec is None:
            raise NotFoundError(f"Item WCP '{item_id}' tidak ditemukan.")
        return _to_item_read(rec)

    def update_item(self, item_id: str, data: WcpItemUpdate) -> WcpItemRead:
        rec = self._s.scalar(select(WcpItemModel).where(WcpItemModel.item_id == item_id))
        if rec is None:
            raise NotFoundError(f"Item WCP '{item_id}' tidak ditemukan.")
        patch = data.model_dump(exclude_unset=True)
        if "pernyataan" in patch:
            rec.pernyataan = patch["pernyataan"]
        if "reverse_type" in patch:
            rec.reverse_type = patch["reverse_type"]
        if "urutan" in patch:
            rec.urutan = patch["urutan"]
        self._s.flush()
        return _to_item_read(rec)
