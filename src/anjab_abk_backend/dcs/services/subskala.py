"""SEAM akses data untuk sub-skala dan item DCS (master data, read-only, seeded)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...errors import NotFoundError
from ..schemas.subskala import DcsItemRead, DcsSubSkalaRead, DcsSubSkalaWithItemsRead
from ..seed import ITEM, SUB_SKALA


@dataclass
class _ItemRecord:
    id: str
    item_id: str
    subskala_kode: str
    sub_dimensi: str
    pernyataan: str
    arah: str
    urutan: int


@dataclass
class _SubSkalaRecord:
    id: str
    kode: str
    nama: str
    urutan: int


class DcsSubSkalaService(Protocol):
    """Kontrak akses master data sub-skala dan item DCS."""

    def list_sub_skala(self) -> list[DcsSubSkalaRead]: ...
    def get_sub_skala(self, kode: str) -> DcsSubSkalaWithItemsRead: ...
    def list_item(self) -> list[DcsItemRead]: ...
    def get_item_by_item_id(self, item_id: str) -> DcsItemRead: ...


def _to_item_read(rec: _ItemRecord) -> DcsItemRead:
    return DcsItemRead.model_validate(rec)


def _to_sub_skala_read(rec: _SubSkalaRecord) -> DcsSubSkalaRead:
    return DcsSubSkalaRead.model_validate(rec)


class InMemoryDcsSubSkalaService:
    """Implementasi seeded in-memory — data identik dengan sheet DCS Screening."""

    def __init__(self) -> None:
        self._sub_skala: dict[str, _SubSkalaRecord] = {}
        self._items: dict[str, _ItemRecord] = {}
        self._seed()

    def _seed(self) -> None:
        for kode, nama, urutan in SUB_SKALA:
            rec = _SubSkalaRecord(id=f"dsk_{kode}", kode=kode, nama=nama, urutan=urutan)
            self._sub_skala[kode] = rec

        for item_id, subskala_kode, sub_dimensi, pernyataan, arah, urutan in ITEM:
            rec = _ItemRecord(
                id=f"ditm_{item_id}",
                item_id=item_id,
                subskala_kode=subskala_kode,
                sub_dimensi=sub_dimensi,
                pernyataan=pernyataan,
                arah=arah,
                urutan=urutan,
            )
            self._items[item_id] = rec

    def list_sub_skala(self) -> list[DcsSubSkalaRead]:
        return [
            _to_sub_skala_read(s) for s in sorted(self._sub_skala.values(), key=lambda x: x.urutan)
        ]

    def get_sub_skala(self, kode: str) -> DcsSubSkalaWithItemsRead:
        rec = self._sub_skala.get(kode)
        if rec is None:
            raise NotFoundError(f"Sub-skala DCS '{kode}' tidak ditemukan.")
        sk_read = _to_sub_skala_read(rec)
        items = [
            _to_item_read(i)
            for i in sorted(self._items.values(), key=lambda x: x.urutan)
            if i.subskala_kode == kode
        ]
        return DcsSubSkalaWithItemsRead(**sk_read.model_dump(), items=items)

    def list_item(self) -> list[DcsItemRead]:
        return [_to_item_read(i) for i in sorted(self._items.values(), key=lambda x: x.urutan)]

    def get_item_by_item_id(self, item_id: str) -> DcsItemRead:
        rec = self._items.get(item_id)
        if rec is None:
            raise NotFoundError(f"Item DCS '{item_id}' tidak ditemukan.")
        return _to_item_read(rec)
