"""Service analisis Task Inventory: himpunan terpilih & agregasi lintas responden.

Agregasi ini menjadi masukan ABK: untuk tiap task terpilih dihitung tingkat relevansi
(berapa partisipan menandai relevan) dan rata-rata beban (jam/minggu, jam/tahun, durasi,
peak), distribusi AI_Mode/VA_Type, serta jumlah penanda risiko DCS.
"""

from __future__ import annotations

import statistics

from ..schemas.catalog import TiCatalogRead
from ..schemas.detail import TiDetailRead
from ..schemas.hasil import TiHasilSesiRead, TiHasilTaskRead, TiTaskTerpilihRead
from ..schemas.sesi import TiSesiRead

MINGGU_EFEKTIF = 45  # jam/tahun = jam/minggu × 45 minggu efektif (standar CalHR sheet TI)


def _pct(n: int, total: int) -> float:
    return round(100.0 * n / total, 2) if total else 0.0


def compute_task_terpilih(
    kodes: list[str],
    catalog_map: dict[str, TiCatalogRead],
    relevan_counts: dict[str, int],
    n_tahap1: int,
) -> list[TiTaskTerpilihRead]:
    """Bangun daftar task terpilih beserta statistik relevansi."""
    rows: list[TiTaskTerpilihRead] = []
    for kode in kodes:
        cat = catalog_map.get(kode)
        n_relevan = relevan_counts.get(kode, 0)
        rows.append(
            TiTaskTerpilihRead(
                kode=kode,
                tugas_pokok=cat.tugas_pokok if cat else "",
                detil_tugas=cat.detil_tugas if cat else "",
                uraian_tugas=cat.uraian_tugas if cat else "",
                n_relevan=n_relevan,
                pct_relevan=_pct(n_relevan, n_tahap1),
                std_sumber_bukti=cat.std_sumber_bukti if cat else None,
                std_kondisi=cat.std_kondisi if cat else None,
                std_frekuensi_teks=cat.std_frekuensi_teks if cat else None,
                std_durasi_per_kali=cat.std_durasi_per_kali if cat else None,
                std_jam_per_minggu=cat.std_jam_per_minggu if cat else None,
                std_peak4w_hours=cat.std_peak4w_hours if cat else None,
                std_ai_mode=cat.std_ai_mode if cat else None,
                std_va_type=cat.std_va_type if cat else None,
                std_dcs_flag=cat.std_dcs_flag if cat else None,
            )
        )
    rows.sort(key=lambda r: (-r.n_relevan, r.kode))
    return rows


def compute_hasil_sesi(
    sesi: TiSesiRead,
    kodes: list[str],
    catalog_map: dict[str, TiCatalogRead],
    relevan_counts: dict[str, int],
    n_tahap1: int,
    detail_records: list[TiDetailRead],
    n_tahap3: int,
) -> TiHasilSesiRead:
    """Hitung agregasi lengkap satu sesi Task Inventory."""
    by_kode: dict[str, list[TiDetailRead]] = {}
    for d in detail_records:
        by_kode.setdefault(d.task_kode, []).append(d)

    tasks: list[TiHasilTaskRead] = []
    total_jpm = 0.0
    for kode in kodes:
        cat = catalog_map.get(kode)
        entries = by_kode.get(kode, [])
        n_detail = len({d.responden_id for d in entries})

        if entries:
            jpm_mean = round(statistics.fmean(d.jam_per_minggu for d in entries), 2)
            durasi_mean = round(statistics.fmean(d.durasi_per_kali for d in entries), 2)
            peak_mean = round(statistics.fmean(d.peak4w_hours for d in entries), 2)
        else:
            jpm_mean = durasi_mean = peak_mean = 0.0

        ai_dist: dict[str, int] = {}
        va_dist: dict[str, int] = {}
        dcs_count = 0
        for d in entries:
            ai_dist[d.ai_mode] = ai_dist.get(d.ai_mode, 0) + 1
            va_dist[d.va_type] = va_dist.get(d.va_type, 0) + 1
            if d.dcs_flag:
                dcs_count += 1

        n_setuju = sum(1 for d in entries if d.setuju_standar)
        n_ubah = len(entries) - n_setuju

        total_jpm += jpm_mean
        tasks.append(
            TiHasilTaskRead(
                kode=kode,
                tugas_pokok=cat.tugas_pokok if cat else "",
                detil_tugas=cat.detil_tugas if cat else "",
                uraian_tugas=cat.uraian_tugas if cat else "",
                n_relevan=relevan_counts.get(kode, 0),
                pct_relevan=_pct(relevan_counts.get(kode, 0), n_tahap1),
                n_detail=n_detail,
                jam_per_minggu_mean=jpm_mean,
                jam_per_tahun_mean=round(jpm_mean * MINGGU_EFEKTIF, 2),
                durasi_per_kali_mean=durasi_mean,
                peak4w_hours_mean=peak_mean,
                ai_mode_dist=ai_dist,
                va_type_dist=va_dist,
                dcs_flag_count=dcs_count,
                n_setuju_standar=n_setuju,
                n_ubah_standar=n_ubah,
            )
        )

    tasks.sort(key=lambda t: (-t.jam_per_tahun_mean, -t.n_relevan, t.kode))
    return TiHasilSesiRead(
        sesi_id=sesi.id,
        jabatan_id=sesi.jabatan_id,
        periode=sesi.periode,
        n_responden_tahap1=n_tahap1,
        n_responden_tahap3=n_tahap3,
        jumlah_task_terpilih=len(kodes),
        total_jam_per_minggu=round(total_jpm, 2),
        total_jam_per_tahun=round(total_jpm * MINGGU_EFEKTIF, 2),
        tasks=tasks,
    )
