"""SEAM akses data catalog Task Inventory (master data, seeded read-only).

`TiCatalogService` adalah kontrak (Protocol). Dua implementasi tersedia:
- `InMemoryTiCatalogService`: seeded langsung dari JSON (fallback/legacy).
- `UraianTugasBackedCatalogService`: baca dari UraianTugasService + DetilTugasService +
  TugasPokokService — sumber tunggal data setelah model catalog dinormalisasi.
  Perubahan via CRUD uraian/detil/tugas-pokok langsung tercermin di catalog.

Catalog dikelompokkan berdasarkan kombinasi (unit × jabatan_id). jabatan_id
diambil langsung dari UraianTugas (M2O, bukan diwarisi dari TugasPokok).
"""

from __future__ import annotations

import hashlib
import threading
from typing import TYPE_CHECKING, Protocol

from ...errors import NotFoundError
from ..schemas.catalog import TiCatalogRead, TiKombinasiRead
from ..seed import load_catalog

if TYPE_CHECKING:
    from ...anjab.services.jabatan import JabatanService
    from .detil_tugas import DetilTugasService
    from .tugas_pokok import TugasPokokService
    from .uraian_tugas import UraianTugasService


def _synth_id(prefix: str, nama: str) -> str:
    """Sintesiskan id deterministik dari nama (hanya untuk fallback in-memory legacy)."""
    digest = hashlib.sha1(nama.encode("utf-8")).hexdigest()[:8]  # noqa: S324
    return f"{prefix}_{digest}"


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
            detil_nama = item["detil_tugas"] or None
            read = TiCatalogRead(
                kode=item["kode"],
                unit=item["unit"],
                jabatan_id=jabatan_id,
                # Legacy in-memory: JSON tak menyimpan id, sintesiskan id stabil dari nama
                # agar kontrak schema terpenuhi & cascade Tahap 1 tetap berfungsi.
                tugas_pokok_id=_synth_id("titp", item["tugas_pokok"]),
                tugas_pokok=item["tugas_pokok"],
                detil_tugas_id=_synth_id("tidt", detil_nama) if detil_nama else None,
                detil_tugas=detil_nama,
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
                TiKombinasiRead(unit=unit, jabatan_id=jid, jabatan_nama=jid, jumlah_task=len(items))
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
    jabatan_id diambil langsung dari UraianTugas (M2O, disimpan eksplisit).
    """

    def __init__(
        self,
        ut_svc: UraianTugasService,
        dt_svc: DetilTugasService,
        tp_svc: TugasPokokService,
        jabatan_svc: JabatanService | None = None,
    ) -> None:
        self._ut = ut_svc
        self._dt = dt_svc
        self._tp = tp_svc
        self._jabatan_svc = jabatan_svc

    def _to_catalog(self, ut) -> TiCatalogRead:  # type: ignore[no-untyped-def]
        dt = self._dt.get(ut.detil_tugas_id) if ut.detil_tugas_id else None
        tp = self._tp.get(ut.tugas_pokok_id)
        return TiCatalogRead(
            kode=ut.kode,
            unit=ut.unit,
            jabatan_id=ut.jabatan_id,
            tugas_pokok_id=ut.tugas_pokok_id,
            tugas_pokok=tp.nama,
            detil_tugas_id=ut.detil_tugas_id,
            detil_tugas=dt.nama if dt else None,
            uraian_tugas=ut.uraian,
            urutan=ut.urutan,
            std_sumber_bukti=ut.std_sumber_bukti,
            std_kondisi=ut.std_kondisi,
            std_frekuensi_teks=ut.std_frekuensi_teks,
            std_durasi_per_kali=ut.std_durasi_per_kali,
            std_jam_per_minggu=ut.std_jam_per_minggu,
            std_peak4w_hours=ut.std_peak4w_hours,
            std_va_type=ut.std_va_type,
        )

    def list_kombinasi(self) -> list[TiKombinasiRead]:
        all_ut, _ = self._ut.list(limit=10_000, offset=0)
        counts: dict[tuple[str, str], int] = {}
        for ut in all_ut:
            key = (ut.unit, ut.jabatan_id)
            counts[key] = counts.get(key, 0) + 1
        jabatan_ids = list({jid for (_, jid) in counts})
        jabatan_map: dict[str, str] = {}
        if self._jabatan_svc:
            for jid in jabatan_ids:
                try:
                    jabatan_map[jid] = self._jabatan_svc.get(jid).nama
                except Exception:
                    jabatan_map[jid] = jid
        rows = [
            TiKombinasiRead(
                unit=unit, jabatan_id=jid, jabatan_nama=jabatan_map.get(jid, jid), jumlah_task=cnt
            )
            for (unit, jid), cnt in counts.items()
        ]
        rows.sort(key=lambda r: (r.unit, r.jabatan_nama))
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
