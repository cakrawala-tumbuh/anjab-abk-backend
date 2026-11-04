"""Fungsi murni (tanpa DB) untuk menghitung hasil analisis OPM.

Formula (dipindah dari sheet `03_Rating_OPM`):
- ``Selection_Essential``  = YA jika ``Importance >= 4 OR Criticality >= 4``
- ``Workload_Essential``   = YA jika ``(Importance >= 3 AND Frequency >= 3) OR Criticality >= 4``

Dihitung dari **mean** per dimensi lintas responden untuk flag agregat sesi, dan
dari nilai individual tiap responden untuk proporsi rater (`prop_*`).
"""

from __future__ import annotations

import statistics

from ..schemas.hasil import OpmHasilSesiRead, OpmHasilTaskRead
from ..schemas.sesi import OpmSesiRead, OpmSesiTaskRead


def _selection_essential(importance: float, criticality: float) -> bool:
    return importance >= 4 or criticality >= 4


def _workload_essential(importance: float, frequency: float, criticality: float) -> bool:
    return (importance >= 3 and frequency >= 3) or criticality >= 4


def compute_hasil_sesi(
    sesi: OpmSesiRead,
    tasks: list[OpmSesiTaskRead],
    responden_raw: list[tuple[str, dict[str, tuple[int, int, int]]]],
    orphan_kodes: frozenset[str] | set[str] = frozenset(),
) -> OpmHasilSesiRead:
    """Hitung hasil agregat sesi OPM dari semua responden yang sudah submit.

    Task tanpa satu pun rating (``n == 0``) TIDAK diberi angka: seluruh ``mean_*`` dan
    kedua flag esensial bernilai ``None`` (bukan 0.0/False) agar kekosongan tidak terbaca
    sebagai nilai (backlog ``#69``). Hal yang sama berlaku untuk ``min_*``/``median_*``/
    ``max_*`` dan ``rating_spread`` (backlog ``#82``): ``rating_spread`` bernilai ``True``
    bila ``max - min >= 2`` pada minimal satu dimensi, murni sinyal telaah yang tidak
    memengaruhi mean, SD, maupun flag esensial.

    Args:
        sesi: Sesi OPM yang dianalisis.
        tasks: Snapshot task sesi.
        responden_raw: List of (responden_id,
            {task_kode: (importance, frequency, criticality)}).
        orphan_kodes: Kode task yang punya baris di register pengecualian sesi; hanya
            dipakai untuk menandai ``orphan`` pada hasil per task.

    Returns:
        Hasil agregat sesi beserta hasil per task.
    """
    task_results: list[OpmHasilTaskRead] = []

    for task in tasks:
        nilai = [raw[task.task_kode] for _, raw in responden_raw if task.task_kode in raw]
        n = len(nilai)

        importances = [v[0] for v in nilai]
        frequencies = [v[1] for v in nilai]
        criticalities = [v[2] for v in nilai]

        mean_importance = round(statistics.mean(importances), 2) if n else None
        mean_frequency = round(statistics.mean(frequencies), 2) if n else None
        mean_criticality = round(statistics.mean(criticalities), 2) if n else None

        sd_importance = round(statistics.stdev(importances), 2) if n >= 2 else None
        sd_frequency = round(statistics.stdev(frequencies), 2) if n >= 2 else None
        sd_criticality = round(statistics.stdev(criticalities), 2) if n >= 2 else None

        sebaran: dict[str, float] = {}
        rating_spread: bool | None = None
        if n:
            for nama, vals in (
                ("importance", importances),
                ("frequency", frequencies),
                ("criticality", criticalities),
            ):
                sebaran[f"min_{nama}"] = float(min(vals))
                sebaran[f"median_{nama}"] = float(statistics.median(vals))
                sebaran[f"max_{nama}"] = float(max(vals))
            rating_spread = any(
                max(vals) - min(vals) >= 2 for vals in (importances, frequencies, criticalities)
            )

        selection_essential: bool | None = None
        workload_essential: bool | None = None
        if n:
            assert mean_importance is not None
            assert mean_frequency is not None
            assert mean_criticality is not None
            selection_essential = _selection_essential(mean_importance, mean_criticality)
            workload_essential = _workload_essential(
                mean_importance, mean_frequency, mean_criticality
            )
            n_sel = sum(1 for imp, _freq, crit in nilai if _selection_essential(imp, crit))
            n_wl = sum(1 for imp, freq, crit in nilai if _workload_essential(imp, freq, crit))
            prop_selection_essential = round(n_sel / n, 4)
            prop_workload_essential = round(n_wl / n, 4)
        else:
            prop_selection_essential = 0.0
            prop_workload_essential = 0.0

        task_results.append(
            OpmHasilTaskRead(
                task_kode=task.task_kode,
                uraian_tugas=task.uraian_tugas,
                tugas_pokok=task.tugas_pokok,
                detil_tugas=task.detil_tugas,
                n=n,
                mean_importance=mean_importance,
                mean_frequency=mean_frequency,
                mean_criticality=mean_criticality,
                sd_importance=sd_importance,
                sd_frequency=sd_frequency,
                sd_criticality=sd_criticality,
                rating_spread=rating_spread,
                **sebaran,
                selection_essential=selection_essential,
                workload_essential=workload_essential,
                prop_selection_essential=prop_selection_essential,
                prop_workload_essential=prop_workload_essential,
                orphan=task.task_kode in orphan_kodes,
            )
        )

    return OpmHasilSesiRead(
        sesi_id=sesi.id,
        jabatan_id=sesi.jabatan_id,
        jabatan_nama=sesi.jabatan_nama,
        cabang=sesi.cabang,
        periode=sesi.periode,
        n_responden_submit=len(responden_raw),
        tasks=task_results,
    )
