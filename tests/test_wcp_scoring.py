"""Unit test logika scoring WCP: reverse scoring, Cronbach's alpha, interpretasi."""

from __future__ import annotations

import pytest

from anjab_abk_backend.wcp.services.analisis import _adjusted, _cronbach_alpha, _interpret

# --- Reverse scoring ---


@pytest.mark.parametrize(
    "skor_raw, reverse_type, expected",
    [
        (1, "NONE", 1.0),
        (4, "NONE", 4.0),
        (5, "NONE", 5.0),
        (1, "R", 5.0),
        (2, "R", 4.0),
        (3, "R", 3.0),
        (4, "R", 2.0),
        (5, "R", 1.0),
        (1, "UF", 1.0),
        (4, "UF", 4.0),
        (1, "R_STAR", 5.0),
        (4, "R_STAR", 2.0),
    ],
)
def test_adjusted(skor_raw: int, reverse_type: str, expected: float) -> None:
    assert _adjusted(skor_raw, reverse_type) == expected


# --- Cronbach's alpha ---


def test_cronbach_perfect_consistency() -> None:
    # Semua responden skor identik → variance item = 0 → alpha = 0
    matrix = [[4.0, 4.0, 4.0, 4.0, 4.0, 4.0]] * 6
    alpha = _cronbach_alpha(matrix)
    assert alpha is None or alpha == pytest.approx(0.0, abs=1e-4)


def test_cronbach_single_responden_returns_none() -> None:
    assert _cronbach_alpha([[4.0, 3.0, 5.0, 4.0, 3.0, 4.0]]) is None


def test_cronbach_reasonable_value() -> None:
    # Matrix dengan variasi yang cukup — alpha harus ≥ 0 dan ≤ 1
    matrix = [
        [4.0, 3.0, 4.0, 5.0, 3.0, 4.0],
        [3.0, 4.0, 3.0, 4.0, 4.0, 3.0],
        [5.0, 5.0, 4.0, 5.0, 5.0, 4.0],
        [2.0, 2.0, 3.0, 3.0, 2.0, 3.0],
        [4.0, 4.0, 4.0, 4.0, 4.0, 4.0],
        [3.0, 3.0, 3.0, 3.0, 3.0, 3.0],
    ]
    alpha = _cronbach_alpha(matrix)
    assert alpha is not None
    assert 0.0 <= alpha <= 1.0


# --- Interpretasi ---


@pytest.mark.parametrize(
    "skor, is_risk, expected",
    [
        (4.5, False, "BAIK"),
        (4.0, False, "BAIK"),
        (3.5, False, "CUKUP"),
        (3.0, False, "CUKUP"),
        (2.9, False, "PERLU_PERHATIAN"),
        (1.0, False, "PERLU_PERHATIAN"),
        (2.0, True, "AMAN"),
        (1.0, True, "AMAN"),
        (2.5, True, "WASPADA"),
        (3.0, True, "WASPADA"),
        (3.1, True, "RISIKO_TINGGI"),
        (5.0, True, "RISIKO_TINGGI"),
    ],
)
def test_interpret(skor: float, is_risk: bool, expected: str) -> None:
    assert _interpret(skor, is_risk) == expected
