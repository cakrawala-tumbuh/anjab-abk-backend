"""Tes unit murni `hitung_saran`: 13 kasus sheet UJI_RUMUS (backlog `#57`).

Kolom Kritis sheet masih kosakata asli; dipetakan `Ya→Ada indikasi`, `Tidak→Tidak terlihat`,
`Belum tahu→Belum tahu`. Sel kosong = K kosong (`None`).
"""

from __future__ import annotations

import pytest

from anjab_abk_backend.redesain.triase import VERSI_ATURAN_TRIASE, hitung_saran

D = "Diperkuat untuk klaim"
TT = "Tidak terlihat"

KASUS = [
    ("T01", D, "Tidak", TT, "Tinggi", "Rendah", "Rendah", "Rendah", "P1 - Utama"),
    ("T02", D, "Tidak", TT, "Rendah", "Tinggi", "Rendah", "Rendah", "P1 - Utama"),
    ("T03", D, "Tidak", TT, "Sedang", "Rendah", "Tinggi", "Tinggi", "P1 - Utama"),
    ("T04", D, "Tidak", TT, "Rendah", "Rendah", "Tinggi", "Rendah", "P2 - Berikutnya"),
    ("T05", D, "Tidak", TT, "Sedang", "Sedang", "Rendah", "Rendah", "P2 - Berikutnya"),
    ("T06", D, "Tidak", TT, "Rendah", "Rendah", "Rendah", "Rendah", "P3 - Pantau"),
    ("T07", "Hipotesis", "Tidak", TT, "Tinggi", "Sedang", "Sedang", "Sedang", "K - Klarifikasi"),
    ("T08", D, "Ya", TT, "Tinggi", "Rendah", "Rendah", "Rendah", "K - Klarifikasi"),
    (
        "T09",
        "Hipotesis",
        "Ya",
        "Ada indikasi",
        "Belum tahu",
        "Belum tahu",
        "Belum tahu",
        "Belum tahu",
        "P0 - Eskalasi",
    ),
    ("T10", D, "Tidak", "Belum tahu", "Tinggi", "Rendah", "Rendah", "Rendah", "K - Klarifikasi"),
    ("T11", D, "Tidak", TT, None, "Rendah", "Rendah", "Rendah", "K - Klarifikasi"),
    ("T12", D, "Tidak", TT, "Tinggi", "Rendah", "Rendah", "Rendah", "P1 - Utama"),
    ("T13", D, "Tidak", TT, "Rendah", "Rendah", "Rendah", "Rendah", "P3 - Pantau"),
]


@pytest.mark.parametrize(
    ("kasus", "status", "gap", "kritis", "k1", "k2", "k3", "k4", "harapan"),
    KASUS,
    ids=[k[0] for k in KASUS],
)
def test_uji_rumus(kasus, status, gap, kritis, k1, k2, k3, k4, harapan):
    assert hitung_saran(status, gap, kritis, k1, k2, k3, k4) == harapan


def test_jumlah_kasus_13_dan_pasangan_identik():
    assert len(KASUS) == 13
    hasil = {k[0]: hitung_saran(*k[1:8]) for k in KASUS}
    assert hasil["T01"] == hasil["T12"]
    assert hasil["T06"] == hasil["T13"]


@pytest.mark.parametrize("k", ["Tinggi", "Sedang", "Rendah"])
def test_belum_cukup_selalu_klarifikasi(k):
    assert hitung_saran("Belum cukup", "Tidak", TT, k, k, k, k) == "K - Klarifikasi"


def test_k_kosong_beda_dari_belum_tahu_dan_rendah():
    assert hitung_saran(D, "Tidak", TT, "Rendah", "Rendah", "Rendah", "Rendah") == "P3 - Pantau"
    assert hitung_saran(D, "Tidak", TT, "Belum tahu", "Rendah", "Rendah", "Rendah") == (
        "K - Klarifikasi"
    )
    assert hitung_saran(D, "Tidak", TT, None, "Rendah", "Rendah", "Rendah") == "K - Klarifikasi"


def test_versi_aturan():
    assert VERSI_ATURAN_TRIASE == "v1.3"
