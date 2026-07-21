"""Service analisis DCS: reverse scoring, Cronbach's alpha, risk flag, K-Index.

Katalog item (sub-skala, keanggotaan item, arah) TIDAK lagi dibaca dari konstanta
seed (`dcs.seed.ITEM`) melainkan diterima sebagai `DcsCatalog` yang dibangun dari
tabel `dcs_item`/`dcs_subskala` (via `DcsSubSkalaService`). Ini membuat perubahan
katalog lewat API — `update_item` (arah) maupun `delete_item` — langsung tercermin
di analisis; dulu analisis membaca seed sehingga hapus/ubah-arah item lewat API
DIABAIKAN diam-diam (setiap responden yang menjawab jumlah item ≠ jumlah item seed
gugur dari agregat sub-skala).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from ..schemas.hasil import (
    DcsHasilRead,
    DcsHasilRespondenRead,
    DcsHasilSubSkalaRead,
    DcsHasilSubSkalaRespondenRead,
    DcsRiskFlag,
)
from ..schemas.subskala import DcsItemRead, DcsSubSkalaRead

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


@dataclass(frozen=True)
class DcsCatalog:
    """Katalog item DCS aktif (snapshot DB) yang dipakai perhitungan analisis.

    Attributes:
        sub_skala_sorted: Daftar ``(kode, nama)`` sub-skala terurut ``urutan``.
        sk_items: Peta ``kode sub-skala -> [item_id]`` terurut ``urutan``.
        item_arah: Peta ``item_id -> arah`` ("F"/"UF").
    """

    sub_skala_sorted: list[tuple[str, str]]
    sk_items: dict[str, list[str]]
    item_arah: dict[str, str]


def build_catalog(
    sub_skala: list[DcsSubSkalaRead],
    items: list[DcsItemRead],
) -> DcsCatalog:
    """Bangun `DcsCatalog` dari hasil baca DB (`list_sub_skala` + `list_item`)."""
    sub_skala_sorted = [(s.kode, s.nama) for s in sorted(sub_skala, key=lambda x: x.urutan)]
    sk_items: dict[str, list[str]] = {}
    for item in sorted(items, key=lambda x: x.urutan):
        sk_items.setdefault(item.subskala_kode, []).append(item.item_id)
    item_arah = {item.item_id: item.arah for item in items}
    return DcsCatalog(
        sub_skala_sorted=sub_skala_sorted,
        sk_items=sk_items,
        item_arah=item_arah,
    )


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


def compute_hasil_responden(
    responden_id: str,
    raw_scores: dict[str, int],
    catalog: DcsCatalog,
) -> DcsHasilRespondenRead:
    """Hitung skor per sub-skala untuk satu responden."""
    sub_skala_results: list[DcsHasilSubSkalaRespondenRead] = []
    scores_by_sk: dict[str, float] = {}

    for kode, nama in catalog.sub_skala_sorted:
        item_ids = catalog.sk_items.get(kode, [])
        adjusted = [
            _adjusted(raw_scores[iid], catalog.item_arah[iid])
            for iid in item_ids
            if iid in raw_scores
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


def compute_hasil(
    responden_raw_scores: list[tuple[str, dict[str, int]]],
    wcp_risk_score: float | None,
    catalog: DcsCatalog,
) -> DcsHasilRead:
    """Hitung hasil agregat instrumen dari semua responden yang sudah submit.

    responden_raw_scores: list of (responden_id, {item_id: skor_raw})
    wcp_risk_score: skor risiko WCP ternormalisasi (0–1), opsional untuk K-Index.
    catalog: katalog item DCS aktif (snapshot DB).
    """
    n = len(responden_raw_scores)
    sub_skala_results: list[DcsHasilSubSkalaRead] = []
    mean_by_sk: dict[str, float] = {}

    for kode, nama in catalog.sub_skala_sorted:
        item_ids = catalog.sk_items.get(kode, [])
        per_responden: list[float] = []
        scores_matrix: list[list[float]] = []

        for _, raw in responden_raw_scores:
            adjusted_row = [
                _adjusted(raw[iid], catalog.item_arah[iid]) for iid in item_ids if iid in raw
            ]
            # Sub-skala tanpa item (item terakhir terhapus) dilewati agar tidak
            # memanggil mean([]); guard hapus juga menolak menghapus item terakhir.
            if item_ids and len(adjusted_row) == len(item_ids):
                per_responden.append(statistics.mean(adjusted_row))
                scores_matrix.append(adjusted_row)

        if not per_responden:
            skor_mean, skor_std = 0.0, 0.0
        else:
            skor_mean = statistics.mean(per_responden)
            skor_std = statistics.stdev(per_responden) if len(per_responden) > 1 else 0.0

        mean_by_sk[kode] = skor_mean
        sub_skala_results.append(
            DcsHasilSubSkalaRead(
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

    return DcsHasilRead(
        n_responden=n,
        sub_skala=sub_skala_results,
        risk_flag=risk_flag,
        k_index=k_index,
        k_index_wcp_risk=wcp_risk_score,
    )
