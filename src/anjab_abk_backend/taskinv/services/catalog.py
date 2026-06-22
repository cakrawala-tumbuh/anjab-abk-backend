"""SEAM akses data catalog Task Inventory (master data, seeded read-only).

`TiCatalogService` adalah kontrak (Protocol). Dua implementasi tersedia:
- `InMemoryTiCatalogService`: seeded langsung dari JSON (fallback/legacy).
- `UraianTugasBackedCatalogService`: baca dari UraianTugasService + DetilTugasService +
  TugasPokokService — sumber tunggal data setelah model catalog dinormalisasi.
  Perubahan via CRUD uraian/detil/tugas-pokok langsung tercermin di catalog.

Catalog dikelompokkan berdasarkan kombinasi (unit × jabatan_id). jabatan_id
diwarisi dari TugasPokok (bukan disimpan di UraianTugas secara langsung).
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Protocol

from ...errors import NotFoundError
from ..schemas.catalog import TiCatalogRead, TiKombinasiRead
from ..seed import load_catalog

if TYPE_CHECKING:
    from .detil_tugas import DetilTugasService
    from .tugas_pokok import TugasPokokService
    from .uraian_tugas import UraianTugasService


class TiCatalogService(Protocol):
    """Kontrak akses catalog task."""

    def list_kombinasi(self) -> list[TiKombinasiRead]: ...
    def list_by_kombinasi(self, unit: str, jabatan_id: str) -> list[TiCatalogRead]: ...
    def list_by_jabatan(self, jabatan_id: str) -> list[TiCatalogRead]: ...
    def get(self, kode: str) -> TiCatalogRead: ...
    def valid_kodes(self, unit: str, jabatan_id: str) -> set[str]: ...
    def valid_kodes_for_jabatan(self, jabatan_id: str) -> set[str]: ...


class InMemoryTiCatalogService:
    """Implementasi seeded in-memory — data identik dengan CSV FGD (dedup).

    Hanya untuk fallback; membutuhkan jabatan_id yang sudah di-resolve ke catalog item.
    Gunakan `UraianTugasBackedCatalogService` untuk deployment aktual.
    """

    def __init__(self, jabatan_id_by_nama: dict[str, str]) -> None:
        """
        Args:
            jabatan_id_by_nama: mapping nama kategori_jabatan → jabatan_id
        """
        self._lock = threading.Lock()
        self._by_kode: dict[str, TiCatalogRead] = {}
        self._by_kombinasi: dict[tuple[str, str], list[TiCatalogRead]] = {}
        for item in load_catalog():
            jabatan_id = jabatan_id_by_nama.get(item["kategori_jabatan"], item["kategori_jabatan"])
            read = TiCatalogRead(
                kode=item["kode"],
                unit=item["unit"],
                jabatan_id=jabatan_id,
                tugas_pokok=item["tugas_pokok"],
                detil_tugas=item["detil_tugas"] or None,
                uraian_tugas=item["uraian_tugas"],
                urutan=item["urutan"],
            )
            self._by_kode[item["kode"]] = read
            key = (item["unit"], jabatan_id)
            self._by_kombinasi.setdefault(key, []).append(read)
        for items in self._by_kombinasi.values():
            items.sort(key=lambda it: it.urutan)

    def list_kombinasi(self) -> list[TiKombinasiRead]:
        with self._lock:
            rows = [
                TiKombinasiRead(unit=unit, jabatan_id=jid, jumlah_task=len(items))
                for (unit, jid), items in self._by_kombinasi.items()
            ]
        rows.sort(key=lambda r: (r.unit, r.jabatan_id))
        return rows

    def list_by_kombinasi(self, unit: str, jabatan_id: str) -> list[TiCatalogRead]:
        with self._lock:
            return list(self._by_kombinasi.get((unit, jabatan_id), []))

    def list_by_jabatan(self, jabatan_id: str) -> list[TiCatalogRead]:
        with self._lock:
            result = [
                it
                for (_unit, jid), its in self._by_kombinasi.items()
                if jid == jabatan_id
                for it in its
            ]
        return result

    def get(self, kode: str) -> TiCatalogRead:
        with self._lock:
            item = self._by_kode.get(kode)
        if item is None:
            raise NotFoundError(f"Task catalog '{kode}' tidak ditemukan.")
        return item

    def valid_kodes(self, unit: str, jabatan_id: str) -> set[str]:
        with self._lock:
            return {it.kode for it in self._by_kombinasi.get((unit, jabatan_id), [])}

    def valid_kodes_for_jabatan(self, jabatan_id: str) -> set[str]:
        with self._lock:
            result: set[str] = set()
            for (_unit, jid), items in self._by_kombinasi.items():
                if jid == jabatan_id:
                    result.update(it.kode for it in items)
            return result


class UraianTugasBackedCatalogService:
    """Catalog yang membaca dari UraianTugasService, DetilTugasService, TugasPokokService.

    Sumber tunggal data setelah model catalog dinormalisasi ke tiga tabel terpisah.
    Perubahan via CRUD langsung tercermin di catalog tanpa sinkronisasi tambahan.
    jabatan_id diambil dari TugasPokok induk melalui ut.tugas_pokok_id.
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
            jabatan_id=tp.jabatan_id,
            tugas_pokok=tp.nama,
            detil_tugas=dt.nama if dt else None,
            uraian_tugas=ut.uraian,
            urutan=ut.urutan,
        )

    def list_kombinasi(self) -> list[TiKombinasiRead]:
        all_ut, _ = self._ut.list(limit=10_000, offset=0)
        counts: dict[tuple[str, str], int] = {}
        for ut in all_ut:
            # jabatan_id sudah ada di UraianTugasRead (denormalisasi)
            key = (ut.unit, ut.jabatan_id)
            counts[key] = counts.get(key, 0) + 1
        rows = [
            TiKombinasiRead(unit=unit, jabatan_id=jid, jumlah_task=cnt)
            for (unit, jid), cnt in counts.items()
        ]
        rows.sort(key=lambda r: (r.unit, r.jabatan_id))
        return rows

    def list_by_kombinasi(self, unit: str, jabatan_id: str) -> list[TiCatalogRead]:
        items = self._ut.list_by_unit_jabatan(unit, jabatan_id)
        return [self._to_catalog(ut) for ut in items]

    def list_by_jabatan(self, jabatan_id: str) -> list[TiCatalogRead]:
        items = self._ut.list_by_jabatan(jabatan_id)
        return [self._to_catalog(ut) for ut in items]

    def get(self, kode: str) -> TiCatalogRead:
        ut = self._ut.get_by_kode(kode)
        return self._to_catalog(ut)

    def valid_kodes(self, unit: str, jabatan_id: str) -> set[str]:
        return self._ut.valid_kodes(unit, jabatan_id)

    def valid_kodes_for_jabatan(self, jabatan_id: str) -> set[str]:
        return self._ut.valid_kodes_for_jabatan(jabatan_id)
