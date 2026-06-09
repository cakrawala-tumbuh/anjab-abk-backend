"""Unit test logika scoring DCS: reverse scoring, risk flag, K-Index, Cronbach's alpha."""

from __future__ import annotations

import pytest

from anjab_abk_backend.dcs.services.analisis import (
    _adjusted,
    _compute_k_index,
    _compute_risk_flag,
    _cronbach_alpha,
)

# --- Reverse scoring ---


@pytest.mark.parametrize(
    "skor_raw, arah, expected",
    [
        (1, "F", 1.0),
        (3, "F", 3.0),
        (5, "F", 5.0),
        (1, "UF", 5.0),
        (2, "UF", 4.0),
        (3, "UF", 3.0),
        (4, "UF", 2.0),
        (5, "UF", 1.0),
    ],
)
def test_adjusted(skor_raw: int, arah: str, expected: float) -> None:
    assert _adjusted(skor_raw, arah) == expected


# --- Risk flag ---


@pytest.mark.parametrize(
    "demand, control, support, expected",
    [
        # HIGH: demand tinggi + control/support rendah
        (4.0, 2.0, 3.0, "HIGH"),
        (4.0, 3.0, 2.0, "HIGH"),
        (4.0, 2.0, 2.0, "HIGH"),
        (3.6, 2.4, 2.4, "HIGH"),
        # MODERATE: demand tinggi saja
        (4.0, 3.0, 3.0, "MODERATE"),
        # MODERATE: control rendah saja
        (3.0, 2.0, 3.0, "MODERATE"),
        # MODERATE: support rendah saja
        (3.0, 3.0, 2.0, "MODERATE"),
        # LOW: tidak ada kondisi
        (3.0, 3.0, 3.0, "LOW"),
        (3.5, 2.5, 2.5, "LOW"),
        (1.0, 5.0, 5.0, "LOW"),
    ],
)
def test_risk_flag(demand: float, control: float, support: float, expected: str) -> None:
    assert _compute_risk_flag(demand, control, support) == expected


# --- K-Index ---


def test_k_index_all_zero() -> None:
    # Demand rendah, control & support tinggi, wcp_risk=0 → k=0
    k = _compute_k_index(1.0, 5.0, 5.0, 0.0)
    assert k == pytest.approx(0.0, abs=1e-4)


def test_k_index_max_demand_only() -> None:
    # Demand maksimum (5), control & support aman, wcp=0
    k = _compute_k_index(5.0, 2.5, 2.5, 0.0)
    assert k == pytest.approx(0.40, abs=1e-4)


def test_k_index_max_control_deficit() -> None:
    # Control minimum (1), demand & support aman, wcp=0
    k = _compute_k_index(3.5, 1.0, 2.5, 0.0)
    assert k == pytest.approx(0.25, abs=1e-4)


def test_k_index_max_support_deficit() -> None:
    # Support minimum (1), demand & control aman, wcp=0
    k = _compute_k_index(3.5, 2.5, 1.0, 0.0)
    assert k == pytest.approx(0.25, abs=1e-4)


def test_k_index_wcp_only() -> None:
    # Semua DCS aman, wcp_risk=1.0
    k = _compute_k_index(3.5, 2.5, 2.5, 1.0)
    assert k == pytest.approx(0.10, abs=1e-4)


def test_k_index_capped_at_one() -> None:
    # Semua komponen maksimum → harus dicap di 1.0
    k = _compute_k_index(5.0, 1.0, 1.0, 1.0)
    assert k <= 1.0


# --- Cronbach's alpha ---


def test_cronbach_single_responden_returns_none() -> None:
    assert _cronbach_alpha([[3.0, 4.0, 2.0, 5.0, 3.0, 4.0]]) is None


def test_cronbach_uniform_scores_returns_none_or_zero() -> None:
    matrix = [[3.0] * 14] * 6
    alpha = _cronbach_alpha(matrix)
    assert alpha is None or alpha == pytest.approx(0.0, abs=1e-4)


def test_cronbach_reasonable_value() -> None:
    matrix = [
        [4.0, 3.0, 4.0, 5.0, 3.0, 4.0, 3.0, 4.0, 4.0, 3.0, 4.0, 5.0, 3.0, 4.0],
        [3.0, 4.0, 3.0, 4.0, 4.0, 3.0, 4.0, 3.0, 3.0, 4.0, 3.0, 4.0, 4.0, 3.0],
        [5.0, 5.0, 4.0, 5.0, 5.0, 4.0, 5.0, 5.0, 4.0, 5.0, 5.0, 4.0, 5.0, 5.0],
        [2.0, 2.0, 3.0, 3.0, 2.0, 3.0, 2.0, 2.0, 3.0, 3.0, 2.0, 3.0, 2.0, 2.0],
        [4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 4.0],
        [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
    ]
    alpha = _cronbach_alpha(matrix)
    assert alpha is not None
    assert 0.0 <= alpha <= 1.0
