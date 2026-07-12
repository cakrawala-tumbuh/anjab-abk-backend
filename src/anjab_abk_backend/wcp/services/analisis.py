"""Service analisis WCP: reverse scoring, Cronbach's alpha, agregasi, interpretasi."""

from __future__ import annotations

import statistics

from ..schemas.hasil import (
    Interpretasi,
    WcpHasilDimensiRead,
    WcpHasilDimensiRespondenRead,
    WcpHasilRead,
    WcpHasilRespondenRead,
)
from ..seed import DIMENSI, ITEM


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


# Pre-build lookup: item_id → (kode_dim, reverse_type)
_ITEM_META: dict[str, tuple[str, str]] = {
    item_id: (kode_dim, rev_type) for item_id, kode_dim, _, _, _, rev_type, _ in ITEM
}

# Pre-build lookup: kode_dim → sorted list of item_ids (urutan)
_DIM_ITEMS: dict[str, list[str]] = {}
for _item_id, _kode_dim, _, _, _, _, _urutan in sorted(ITEM, key=lambda x: x[6]):
    _DIM_ITEMS.setdefault(_kode_dim, []).append(_item_id)

# Pre-build dimensi meta: kode → (nama, is_risk)
_DIM_META: dict[str, tuple[str, bool]] = {
    kode: (nama, is_risk) for kode, nama, _, is_risk in DIMENSI
}


# Sorted list of (kode, nama, is_risk) by urutan — used in computation loops
_DIMENSI_SORTED: list[tuple[str, str, bool]] = [
    (kode, nama, is_risk) for kode, nama, _urutan, is_risk in sorted(DIMENSI, key=lambda x: x[2])
]


def compute_hasil_responden(
    responden_id: str,
    raw_scores: dict[str, int],
) -> WcpHasilRespondenRead:
    """Hitung skor per dimensi untuk satu responden."""
    dimensi_results: list[WcpHasilDimensiRespondenRead] = []

    for kode_dim, nama, is_risk in _DIMENSI_SORTED:
        item_ids = _DIM_ITEMS.get(kode_dim, [])
        adjusted = [
            _adjusted(raw_scores[iid], _ITEM_META[iid][1]) for iid in item_ids if iid in raw_scores
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
) -> WcpHasilRead:
    """Hitung hasil agregat instrumen dari semua responden yang sudah submit.

    responden_raw_scores: list of (responden_id, {item_id: skor_raw})
    """
    n = len(responden_raw_scores)
    dimensi_results: list[WcpHasilDimensiRead] = []

    for kode_dim, nama, is_risk in _DIMENSI_SORTED:
        item_ids = _DIM_ITEMS.get(kode_dim, [])

        per_responden: list[float] = []
        scores_matrix: list[list[float]] = []

        for _, raw in responden_raw_scores:
            adjusted_row = [
                _adjusted(raw[iid], _ITEM_META[iid][1]) for iid in item_ids if iid in raw
            ]
            if len(adjusted_row) == len(item_ids):
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
