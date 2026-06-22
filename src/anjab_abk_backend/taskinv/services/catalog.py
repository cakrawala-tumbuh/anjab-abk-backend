"""SEAM akses data catalog Task Inventory (master data, seeded read-only).

`TiCatalogService` adalah kontrak (Protocol). Dua implementasi tersedia:
- `InMemoryTiCatalogService`: seeded langsung dari JSON (fallback/legacy).
- `UraianTugasBackedCatalogService`: baca dari UraianTugasService + DetilTugasService +
  TugasPokokService — sumber tunggal data setelah model catalog dinormalisasi.
  Perubahan via CRUD uraian/detil/tugas-pokok langsung tercermin di catalog.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Protocol

from ...errors import NotFoundError
from ..schemas.catalog import TiCatalogRead, TiKombinasiRead
from ..seed import CatalogItem, load_catalog

if TYPE_CHECKING:
    from .detil_tugas import DetilTugasService
    from .tugas_pokok import TugasPokokService
    from .uraian_tugas import UraianTugasService


class TiCatalogService(Protocol):
    """Kontrak akses catalog task."""

    def list_kombinasi(self) -> list[TiKombinasiRead]: ...
    def list_by_kombinasi(self, unit: str, kategori_jabatan: str) -> list[TiCatalogRead]: ...
    def list_by_kategori(self, kategori_jabatan: str) -> list[TiCatalogRead]: ...
    def get(self, kode: str) -> TiCatalogRead: ...
    def valid_kodes(self, unit: str, kategori_jabatan: str) -> set[str]: ...
    def valid_kodes_for_kategori(self, kategori_jabatan: str) -> set[str]: ...


class InMemoryTiCatalogService:
    """Implementasi seeded in-memory — data identik dengan CSV FGD (dedup).

    Digunakan sebagai fallback. Untuk production gunakan `UraianTugasBackedCatalogService`
    agar perubahan CRUD tercermin di catalog.
    """

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

    def list_by_kategori(self, kategori_jabatan: str) -> list[TiCatalogRead]:
        with self._lock:
            items = [
                it
                for (_unit, kj), its in self._by_kombinasi.items()
                if kj == kategori_jabatan
                for it in its
            ]
        return [TiCatalogRead.model_validate(it) for it in items]

    def valid_kodes(self, unit: str, kategori_jabatan: str) -> set[str]:
        with self._lock:
            items = self._by_kombinasi.get((unit, kategori_jabatan), [])
            return {it["kode"] for it in items}

    def valid_kodes_for_kategori(self, kategori_jabatan: str) -> set[str]:
        with self._lock:
            result: set[str] = set()
            for (_unit, kj), items in self._by_kombinasi.items():
                if kj == kategori_jabatan:
                    result.update(it["kode"] for it in items)
            return result


class UraianTugasBackedCatalogService:
    """Catalog yang membaca dari UraianTugasService, DetilTugasService, TugasPokokService.

    Sumber tunggal data setelah model catalog dinormalisasi ke tiga tabel terpisah.
    Perubahan via CRUD langsung tercermin di catalog tanpa sinkronisasi tambahan.
    """

    def __init__(
        self,
        ut_svc: UraianTugasService,
        dt_svc: DetilTugasService,
        tp_svc: TugasPokokService,
    ) -> None:
        self._ut = ut_svc
        self._dt = dt_svc
        self._tp = tp_svc

    def _to_catalog(self, ut) -> TiCatalogRead:  # type: ignore[no-untyped-def]
        dt = self._dt.get(ut.detil_tugas_id) if ut.detil_tugas_id else None
        tp = self._tp.get(ut.tugas_pokok_id)
        return TiCatalogRead(
            kode=ut.kode,
            unit=ut.unit,
            kategori_jabatan=ut.kategori_jabatan,
            tugas_pokok=tp.nama,
            detil_tugas=dt.nama if dt else None,
            uraian_tugas=ut.uraian,
            urutan=ut.urutan,
        )

    def list_kombinasi(self) -> list[TiKombinasiRead]:
        # Ambil semua uraian_tugas, kumpulkan kombinasi unik
        all_ut, total = self._ut.list(limit=10_000, offset=0)
        counts: dict[tuple[str, str], int] = {}
        for ut in all_ut:
            key = (ut.unit, ut.kategori_jabatan)
            counts[key] = counts.get(key, 0) + 1
        rows = [
            TiKombinasiRead(unit=unit, kategori_jabatan=kj, jumlah_task=cnt)
            for (unit, kj), cnt in counts.items()
        ]
        rows.sort(key=lambda r: (r.unit, r.kategori_jabatan))
        return rows

    def list_by_kombinasi(self, unit: str, kategori_jabatan: str) -> list[TiCatalogRead]:
        items = self._ut.list_by_unit_kategori(unit, kategori_jabatan)
        return [self._to_catalog(ut) for ut in items]

    def list_by_kategori(self, kategori_jabatan: str) -> list[TiCatalogRead]:
        kombinasi = self.list_kombinasi()
        result: list[TiCatalogRead] = []
        for row in kombinasi:
            if row.kategori_jabatan == kategori_jabatan:
                result.extend(self.list_by_kombinasi(row.unit, row.kategori_jabatan))
        return result

    def get(self, kode: str) -> TiCatalogRead:
        ut = self._ut.get_by_kode(kode)
        return self._to_catalog(ut)

    def valid_kodes(self, unit: str, kategori_jabatan: str) -> set[str]:
        return self._ut.valid_kodes(unit, kategori_jabatan)

    def valid_kodes_for_kategori(self, kategori_jabatan: str) -> set[str]:
        kombinasi = self.list_kombinasi()
        result: set[str] = set()
        for row in kombinasi:
            if row.kategori_jabatan == kategori_jabatan:
                result.update(self.valid_kodes(row.unit, row.kategori_jabatan))
        return result
