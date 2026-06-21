"""SEAM akses data catalog Task Inventory (master data, seeded read-only).

Data di-seed dari `taskinv.seed.load_catalog()`. Implementasi in-memory ini placeholder —
diganti penyimpanan persisten oleh `backend-postgresql-skill` tanpa mengubah signature.
"""

from __future__ import annotations

import threading
from typing import Protocol

from ...errors import NotFoundError
from ..schemas.catalog import TiCatalogRead, TiKombinasiRead
from ..seed import CatalogItem, load_catalog


class TiCatalogService(Protocol):
    """Kontrak akses catalog task."""

    def list_kombinasi(self) -> list[TiKombinasiRead]: ...
    def list_by_kombinasi(self, unit: str, kategori_jabatan: str) -> list[TiCatalogRead]: ...
    def get(self, kode: str) -> TiCatalogRead: ...
    def valid_kodes(self, unit: str, kategori_jabatan: str) -> set[str]: ...


class InMemoryTiCatalogService:
    """Implementasi seeded in-memory — data identik dengan CSV FGD (dedup)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._by_kode: dict[str, CatalogItem] = {}
        self._by_kombinasi: dict[tuple[str, str], list[CatalogItem]] = {}
        for item in load_catalog():
            self._by_kode[item["kode"]] = item
            key = (item["unit"], item["kategori_jabatan"])
            self._by_kombinasi.setdefault(key, []).append(item)
        for items in self._by_kombinasi.values():
            items.sort(key=lambda it: it["urutan"])

    def list_kombinasi(self) -> list[TiKombinasiRead]:
        with self._lock:
            rows = [
                TiKombinasiRead(unit=unit, kategori_jabatan=kj, jumlah_task=len(items))
                for (unit, kj), items in self._by_kombinasi.items()
            ]
        rows.sort(key=lambda r: (r.unit, r.kategori_jabatan))
        return rows

    def list_by_kombinasi(self, unit: str, kategori_jabatan: str) -> list[TiCatalogRead]:
        with self._lock:
            items = self._by_kombinasi.get((unit, kategori_jabatan), [])
            return [TiCatalogRead.model_validate(it) for it in items]

    def get(self, kode: str) -> TiCatalogRead:
        with self._lock:
            item = self._by_kode.get(kode)
        if item is None:
            raise NotFoundError(f"Task catalog '{kode}' tidak ditemukan.")
        return TiCatalogRead.model_validate(item)

    def valid_kodes(self, unit: str, kategori_jabatan: str) -> set[str]:
        with self._lock:
            items = self._by_kombinasi.get((unit, kategori_jabatan), [])
            return {it["kode"] for it in items}
