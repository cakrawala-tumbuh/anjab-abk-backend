"""SEAM akses data untuk dimensi dan item WCP (master data, read-only, seeded).

Data di-seed saat inisialisasi dari `wcp.seed`. Tidak ada operasi tulis lewat API.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...errors import NotFoundError
from ..schemas.dimensi import WcpDimensiRead, WcpDimensiWithItemsRead, WcpItemRead
from ..seed import DIMENSI, ITEM


@dataclass
class _ItemRecord:
    id: str
    item_id: str
    dimensi_kode: str
    indikator_kode: str
    indikator_label: str
    pernyataan: str
    reverse_type: str
    urutan: int


@dataclass
class _DimensiRecord:
    id: str
    kode: str
    nama: str
    urutan: int
    is_risk: bool


class WcpDimensiService(Protocol):
    """Kontrak akses master data dimensi dan item WCP."""

    def list_dimensi(self) -> list[WcpDimensiRead]: ...
    def get_dimensi(self, kode: str) -> WcpDimensiWithItemsRead: ...
    def list_item(self) -> list[WcpItemRead]: ...
    def get_item_by_item_id(self, item_id: str) -> WcpItemRead: ...


def _to_item_read(rec: _ItemRecord) -> WcpItemRead:
    return WcpItemRead.model_validate(rec)


def _to_dimensi_read(rec: _DimensiRecord) -> WcpDimensiRead:
    return WcpDimensiRead.model_validate(rec)


class InMemoryWcpDimensiService:
    """Implementasi seeded in-memory — data identik dengan sheet WCP Survey."""

    def __init__(self) -> None:
        self._dimensi: dict[str, _DimensiRecord] = {}
        self._items: dict[str, _ItemRecord] = {}
        self._seed()

    def _seed(self) -> None:
        for kode, nama, urutan, is_risk in DIMENSI:
            rec = _DimensiRecord(
                id=f"wdim_{kode}",
                kode=kode,
                nama=nama,
                urutan=urutan,
                is_risk=is_risk,
            )
            self._dimensi[kode] = rec

        for item_id, kode_dim, ind_kode, ind_label, pernyataan, rev_type, urutan in ITEM:
            rec = _ItemRecord(
                id=f"witm_{item_id}",
                item_id=item_id,
                dimensi_kode=kode_dim,
                indikator_kode=ind_kode,
                indikator_label=ind_label,
                pernyataan=pernyataan,
                reverse_type=rev_type,
                urutan=urutan,
            )
            self._items[item_id] = rec

    def list_dimensi(self) -> list[WcpDimensiRead]:
        return [_to_dimensi_read(d) for d in sorted(self._dimensi.values(), key=lambda x: x.urutan)]

    def get_dimensi(self, kode: str) -> WcpDimensiWithItemsRead:
        rec = self._dimensi.get(kode)
        if rec is None:
            raise NotFoundError(f"Dimensi WCP '{kode}' tidak ditemukan.")
        dim_read = _to_dimensi_read(rec)
        items = [
            _to_item_read(i)
            for i in sorted(self._items.values(), key=lambda x: x.urutan)
            if i.dimensi_kode == kode
        ]
        return WcpDimensiWithItemsRead(**dim_read.model_dump(), items=items)

    def list_item(self) -> list[WcpItemRead]:
        return [_to_item_read(i) for i in sorted(self._items.values(), key=lambda x: x.urutan)]

    def get_item_by_item_id(self, item_id: str) -> WcpItemRead:
        rec = self._items.get(item_id)
        if rec is None:
            raise NotFoundError(f"Item WCP '{item_id}' tidak ditemukan.")
        return _to_item_read(rec)
