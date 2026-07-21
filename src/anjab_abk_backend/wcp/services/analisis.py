"""Service analisis WCP: reverse scoring, Cronbach's alpha, agregasi, interpretasi.

Katalog item (dimensi, keanggotaan item, reverse_type, is_risk) TIDAK lagi dibaca
dari konstanta seed (`wcp.seed`) melainkan diterima sebagai `WcpCatalog` yang
dibangun dari tabel `wcp_item`/`wcp_dimensi` (via `WcpDimensiService`). Perubahan
katalog lewat API (`update_item` reverse_type / `delete_item`) kini langsung
tercermin di analisis; dulu analisis membaca seed sehingga perubahan API diabaikan.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from ..schemas.dimensi import WcpDimensiRead, WcpItemRead
from ..schemas.hasil import (
    Interpretasi,
    WcpHasilDimensiRead,
    WcpHasilDimensiRespondenRead,
    WcpHasilRead,
    WcpHasilRespondenRead,
)


@dataclass(frozen=True)
class WcpCatalog:
    """Katalog item WCP aktif (snapshot DB) yang dipakai perhitungan analisis.

    Attributes:
        dimensi_sorted: Daftar ``(kode, nama, is_risk)`` dimensi terurut ``urutan``.
        dim_items: Peta ``kode dimensi -> [item_id]`` terurut ``urutan``.
        item_reverse: Peta ``item_id -> reverse_type``.
    """

    dimensi_sorted: list[tuple[str, str, bool]]
    dim_items: dict[str, list[str]]
    item_reverse: dict[str, str]


def build_catalog(
    dimensi: list[WcpDimensiRead],
    items: list[WcpItemRead],
) -> WcpCatalog:
    """Bangun `WcpCatalog` dari hasil baca DB (`list_dimensi` + `list_item`)."""
    dimensi_sorted = [(d.kode, d.nama, d.is_risk) for d in sorted(dimensi, key=lambda x: x.urutan)]
    dim_items: dict[str, list[str]] = {}
    for item in sorted(items, key=lambda x: x.urutan):
        dim_items.setdefault(item.dimensi_kode, []).append(item.item_id)
    item_reverse = {item.item_id: item.reverse_type for item in items}
    return WcpCatalog(
        dimensi_sorted=dimensi_sorted,
        dim_items=dim_items,
        item_reverse=item_reverse,
    )


def _adjusted(skor_raw: int, reverse_type: str) -> float:
    if reverse_type in ("R", "R_STAR"):
        return 6.0 - skor_raw
    return float(skor_raw)


def _interpret(skor: float, is_risk: bool) -> Interpretasi:
    if is_risk:
        if skor <= 2.0:
            return "AMAN"
        if skor <= 3.0:
            return "WASPADA"
        return "RISIKO_TINGGI"
    if skor >= 4.0:
        return "BAIK"
    if skor >= 3.0:
        return "CUKUP"
    return "PERLU_PERHATIAN"


def _cronbach_alpha(scores_matrix: list[list[float]]) -> float | None:
    """Hitung Cronbach's alpha dari matrix (n_responden × k_item)."""
    n = len(scores_matrix)
    if n < 2:
        return None
    k = len(scores_matrix[0])
    if k < 2:
        return None

    item_vars = []
    for j in range(k):
        col = [scores_matrix[i][j] for i in range(n)]
        item_vars.append(statistics.variance(col))

    totals = [sum(row) for row in scores_matrix]
    total_var = statistics.variance(totals)

    if total_var == 0:
        return None

    alpha = (k / (k - 1)) * (1.0 - sum(item_vars) / total_var)
    return round(alpha, 4)


def compute_hasil_responden(
    responden_id: str,
    raw_scores: dict[str, int],
    catalog: WcpCatalog,
) -> WcpHasilRespondenRead:
    """Hitung skor per dimensi untuk satu responden."""
    dimensi_results: list[WcpHasilDimensiRespondenRead] = []

    for kode_dim, nama, is_risk in catalog.dimensi_sorted:
        item_ids = catalog.dim_items.get(kode_dim, [])
        adjusted = [
            _adjusted(raw_scores[iid], catalog.item_reverse[iid])
            for iid in item_ids
            if iid in raw_scores
        ]
        skor = statistics.mean(adjusted) if adjusted else 0.0
        dimensi_results.append(
            WcpHasilDimensiRespondenRead(
                dimensi_kode=kode_dim,
                dimensi_nama=nama,
                is_risk=is_risk,
                skor=round(skor, 4),
                interpretasi=_interpret(skor, is_risk),
            )
        )

    return WcpHasilRespondenRead(responden_id=responden_id, dimensi=dimensi_results)


def compute_hasil(
    responden_raw_scores: list[tuple[str, dict[str, int]]],
    catalog: WcpCatalog,
) -> WcpHasilRead:
    """Hitung hasil agregat instrumen dari semua responden yang sudah submit.

    responden_raw_scores: list of (responden_id, {item_id: skor_raw})
    catalog: katalog item WCP aktif (snapshot DB).
    """
    n = len(responden_raw_scores)
    dimensi_results: list[WcpHasilDimensiRead] = []

    for kode_dim, nama, is_risk in catalog.dimensi_sorted:
        item_ids = catalog.dim_items.get(kode_dim, [])

        per_responden: list[float] = []
        scores_matrix: list[list[float]] = []

        for _, raw in responden_raw_scores:
            adjusted_row = [
                _adjusted(raw[iid], catalog.item_reverse[iid]) for iid in item_ids if iid in raw
            ]
            # Dimensi tanpa item (item terakhir terhapus) dilewati agar tidak
            # memanggil mean([]); guard hapus juga menolak menghapus item terakhir.
            if item_ids and len(adjusted_row) == len(item_ids):
                per_responden.append(statistics.mean(adjusted_row))
                scores_matrix.append(adjusted_row)

        if not per_responden:
            skor_mean, skor_std = 0.0, 0.0
        else:
            skor_mean = statistics.mean(per_responden)
            skor_std = statistics.stdev(per_responden) if len(per_responden) > 1 else 0.0

        dimensi_results.append(
            WcpHasilDimensiRead(
                dimensi_kode=kode_dim,
                dimensi_nama=nama,
                is_risk=is_risk,
                n_responden=len(per_responden),
                skor_mean=round(skor_mean, 4),
                skor_std=round(skor_std, 4),
                cronbach_alpha=_cronbach_alpha(scores_matrix),
                interpretasi=_interpret(skor_mean, is_risk),
            )
        )

    return WcpHasilRead(
        n_responden=n,
        dimensi=dimensi_results,
    )
