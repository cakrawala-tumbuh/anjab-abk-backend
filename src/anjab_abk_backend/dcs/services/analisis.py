"""Service analisis DCS: reverse scoring, Cronbach's alpha, risk flag, K-Index."""

from __future__ import annotations

import statistics

from ..schemas.hasil import (
    DcsHasilRespondenRead,
    DcsHasilSesiRead,
    DcsHasilSubSkalaRespondenRead,
    DcsHasilSubSkalaSesiRead,
    DcsRiskFlag,
)
from ..schemas.sesi import DcsSesiRead
from ..seed import ITEM, SUB_SKALA

# Threshold interpretasi DCS (Karasek model)
_DEMAND_HIGH_THRESHOLD = 3.5
_CONTROL_LOW_THRESHOLD = 2.5
_SUPPORT_LOW_THRESHOLD = 2.5

# Normalization ranges untuk K-Index
# DemandPressure: pressure mulai dari threshold, max di skor 5
_DEMAND_NORM_RANGE = 5.0 - _DEMAND_HIGH_THRESHOLD  # = 1.5
# ControlDeficit / SupportDeficit: deficit mulai dari threshold, max di skor 1
_CONTROL_NORM_RANGE = _CONTROL_LOW_THRESHOLD - 1.0  # = 1.5
_SUPPORT_NORM_RANGE = _SUPPORT_LOW_THRESHOLD - 1.0  # = 1.5


def _adjusted(skor_raw: int, arah: str) -> float:
    """Reverse-score item UF; item F dikembalikan apa adanya."""
    if arah == "UF":
        return 6.0 - skor_raw
    return float(skor_raw)


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


def _compute_risk_flag(skor_demand: float, skor_control: float, skor_support: float) -> DcsRiskFlag:
    high_demand = skor_demand > _DEMAND_HIGH_THRESHOLD
    low_control = skor_control < _CONTROL_LOW_THRESHOLD
    low_support = skor_support < _SUPPORT_LOW_THRESHOLD
    if high_demand and (low_control or low_support):
        return "HIGH"
    if high_demand or low_control or low_support:
        return "MODERATE"
    return "LOW"


def _compute_k_index(
    skor_demand: float,
    skor_control: float,
    skor_support: float,
    wcp_risk: float,
) -> float:
    """Hitung K-Index psikososial (0–1).

    K = 0,40×DemandPressure + 0,25×ControlDeficit + 0,25×SupportDeficit + 0,10×WCPRisk

    Semua komponen dinormalisasi ke rentang 0–1.
    """
    demand_pressure = max(0.0, (skor_demand - _DEMAND_HIGH_THRESHOLD) / _DEMAND_NORM_RANGE)
    control_deficit = max(0.0, (_CONTROL_LOW_THRESHOLD - skor_control) / _CONTROL_NORM_RANGE)
    support_deficit = max(0.0, (_SUPPORT_LOW_THRESHOLD - skor_support) / _SUPPORT_NORM_RANGE)

    k = 0.40 * demand_pressure + 0.25 * control_deficit + 0.25 * support_deficit + 0.10 * wcp_risk
    return round(min(1.0, k), 4)


# Pre-build lookup: item_id → arah
_ITEM_ARAH: dict[str, str] = {item_id: arah for item_id, _, _, _, arah, _ in ITEM}

# Pre-build lookup: subskala_kode → sorted list of item_ids
_SK_ITEMS: dict[str, list[str]] = {}
for _item_id, _sk_kode, _, _, _, _urutan in sorted(ITEM, key=lambda x: x[5]):
    _SK_ITEMS.setdefault(_sk_kode, []).append(_item_id)

# Sorted sub-skala list by urutan
_SUB_SKALA_SORTED: list[tuple[str, str]] = [
    (kode, nama) for kode, nama, _urutan in sorted(SUB_SKALA, key=lambda x: x[2])
]


def compute_hasil_responden(
    responden_id: str,
    raw_scores: dict[str, int],
) -> DcsHasilRespondenRead:
    """Hitung skor per sub-skala untuk satu responden."""
    sub_skala_results: list[DcsHasilSubSkalaRespondenRead] = []
    scores_by_sk: dict[str, float] = {}

    for kode, nama in _SUB_SKALA_SORTED:
        item_ids = _SK_ITEMS.get(kode, [])
        adjusted = [
            _adjusted(raw_scores[iid], _ITEM_ARAH[iid]) for iid in item_ids if iid in raw_scores
        ]
        skor = statistics.mean(adjusted) if adjusted else 0.0
        scores_by_sk[kode] = skor
        sub_skala_results.append(
            DcsHasilSubSkalaRespondenRead(
                subskala_kode=kode,
                subskala_nama=nama,
                skor=round(skor, 4),
            )
        )

    risk_flag = _compute_risk_flag(
        scores_by_sk.get("DEMAND", 0.0),
        scores_by_sk.get("CONTROL", 5.0),
        scores_by_sk.get("SUPPORT", 5.0),
    )

    return DcsHasilRespondenRead(
        responden_id=responden_id,
        sub_skala=sub_skala_results,
        risk_flag=risk_flag,
    )


def compute_hasil_sesi(
    sesi: DcsSesiRead,
    responden_raw_scores: list[tuple[str, dict[str, int]]],
    wcp_risk_score: float | None = None,
) -> DcsHasilSesiRead:
    """Hitung hasil agregat sesi dari semua responden yang sudah submit.

    responden_raw_scores: list of (responden_id, {item_id: skor_raw})
    wcp_risk_score: skor risiko WCP ternormalisasi (0–1), opsional untuk K-Index.
    """
    n = len(responden_raw_scores)
    sub_skala_results: list[DcsHasilSubSkalaSesiRead] = []
    mean_by_sk: dict[str, float] = {}

    for kode, nama in _SUB_SKALA_SORTED:
        item_ids = _SK_ITEMS.get(kode, [])
        per_responden: list[float] = []
        scores_matrix: list[list[float]] = []

        for _, raw in responden_raw_scores:
            adjusted_row = [_adjusted(raw[iid], _ITEM_ARAH[iid]) for iid in item_ids if iid in raw]
            if len(adjusted_row) == len(item_ids):
                per_responden.append(statistics.mean(adjusted_row))
                scores_matrix.append(adjusted_row)

        if not per_responden:
            skor_mean, skor_std = 0.0, 0.0
        else:
            skor_mean = statistics.mean(per_responden)
            skor_std = statistics.stdev(per_responden) if len(per_responden) > 1 else 0.0

        mean_by_sk[kode] = skor_mean
        sub_skala_results.append(
            DcsHasilSubSkalaSesiRead(
                subskala_kode=kode,
                subskala_nama=nama,
                n_responden=len(per_responden),
                skor_mean=round(skor_mean, 4),
                skor_std=round(skor_std, 4),
                cronbach_alpha=_cronbach_alpha(scores_matrix),
            )
        )

    risk_flag = _compute_risk_flag(
        mean_by_sk.get("DEMAND", 0.0),
        mean_by_sk.get("CONTROL", 5.0),
        mean_by_sk.get("SUPPORT", 5.0),
    )

    k_index: float | None = None
    if wcp_risk_score is not None:
        k_index = _compute_k_index(
            mean_by_sk.get("DEMAND", 0.0),
            mean_by_sk.get("CONTROL", 5.0),
            mean_by_sk.get("SUPPORT", 5.0),
            wcp_risk_score,
        )

    return DcsHasilSesiRead(
        sesi_id=sesi.id,
        jabatan_id=sesi.jabatan_id,
        periode=sesi.periode,
        n_responden=n,
        sub_skala=sub_skala_results,
        risk_flag=risk_flag,
        k_index=k_index,
        k_index_wcp_risk=wcp_risk_score,
    )
