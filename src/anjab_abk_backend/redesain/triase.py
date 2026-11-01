"""Aturan saran triase otomatis penilaian redesain (port rumus workbook `PENILAIAN!J5`).

Modul ini murni (tanpa I/O, tanpa DB) sehingga dapat diuji langsung terhadap 13 kasus
sheet `UJI_RUMUS`. Kosakata indikasi kritis memakai istilah Lembar Konfirmasi bagian E
(`Ada indikasi` / `Tidak terlihat` / `Belum tahu`) dengan logika rumus asli tetap.
"""

from __future__ import annotations

VERSI_ATURAN_TRIASE = "v1.3"
"""Versi aturan triase yang diterapkan `hitung_saran` (disimpan di tiap penilaian)."""

SARAN_P0 = "P0 - Eskalasi"
SARAN_K = "K - Klarifikasi"
SARAN_P1 = "P1 - Utama"
SARAN_P2 = "P2 - Berikutnya"
SARAN_P3 = "P3 - Pantau"


def hitung_saran(
    status_bukti: str,
    gap_material: str,
    indikasi_kritis: str,
    k1: str | None,
    k2: str | None,
    k3: str | None,
    k4: str | None,
) -> str:
    """Hitung saran triase sebuah penilaian secara deterministik.

    Aturan dievaluasi berurutan dan berhenti di yang pertama cocok:

    1. `indikasi_kritis == "Ada indikasi"` → `P0 - Eskalasi`.
    2. Status bukti bukan `Diperkuat untuk klaim`, gap bukan `Tidak`, indikasi bukan
       `Tidak terlihat`, ada K kosong, atau ada K `Belum tahu` → `K - Klarifikasi`.
    3. K1 atau K2 `Tinggi`, atau K3 dan K4 keduanya `Tinggi` → `P1 - Utama`.
    4. K3 atau K4 `Tinggi`, atau jumlah K `Sedang` ≥ 2 → `P2 - Berikutnya`.
    5. Selain itu → `P3 - Pantau`.

    K kosong (`None`), `Belum tahu`, dan `Rendah` adalah tiga hal berbeda.

    Args:
        status_bukti: Status dengan bukti (`StatusBukti`).
        gap_material: Apakah gap masih material (`YaTidak`).
        indikasi_kritis: Indikasi risiko kritis (`Indikasi`).
        k1: Skala kriteria K1 (`Skala`) atau `None` bila belum diisi.
        k2: Skala kriteria K2 atau `None`.
        k3: Skala kriteria K3 atau `None`.
        k4: Skala kriteria K4 atau `None`.

    Returns:
        Salah satu dari `P0 - Eskalasi`, `K - Klarifikasi`, `P1 - Utama`,
        `P2 - Berikutnya`, `P3 - Pantau`.

    Example:
        >>> hitung_saran("Diperkuat untuk klaim", "Tidak", "Tidak terlihat",
        ...              "Tinggi", "Rendah", "Rendah", "Rendah")
        'P1 - Utama'
    """
    ks = (k1, k2, k3, k4)
    if indikasi_kritis == "Ada indikasi":
        return SARAN_P0
    if (
        status_bukti != "Diperkuat untuk klaim"
        or gap_material != "Tidak"
        or indikasi_kritis != "Tidak terlihat"
        or any(k is None for k in ks)
        or any(k == "Belum tahu" for k in ks)
    ):
        return SARAN_K
    if k1 == "Tinggi" or k2 == "Tinggi" or (k3 == "Tinggi" and k4 == "Tinggi"):
        return SARAN_P1
    if k3 == "Tinggi" or k4 == "Tinggi" or sum(k == "Sedang" for k in ks) >= 2:
        return SARAN_P2
    return SARAN_P3
