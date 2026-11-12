"""Skema metrik alur narasi (UX-13): `GET /api/v1/narasi/metrik`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

BATAS_RENTANG_HARI = 366
"""Rentang tanggal terpanjang (inklusif) yang boleh diminta sekali panggil."""

DESKRIPSI_METRIK = (
    "Definisi operasional (rentang tanggal inklusif, hari UTC). "
    "`jumlah_keputusan` = event TEAM_APPROVE + TEAM_REVISE + TEAM_REJECT + NEED_SOURCE "
    "pada `event_at` dalam rentang. `correction_rate` = TEAM_REVISE / jumlah_keputusan; "
    "`rejection_rate` = TEAM_REJECT / jumlah_keputusan; null bila penyebut 0. "
    "`source_coverage` = proporsi versi narasi yang dibuat dalam rentang dan punya minimal satu "
    "tautan sumber; null bila tak ada versi. `menit_aktif_total` = jumlah detak menit aktif "
    "(satu baris = satu menit) dalam rentang; `menit_aktif_median_per_kasus` = median menit "
    "aktif per kasus atas kasus ber-menit > 0; null bila tak ada. Waktu = menit aktif, bukan "
    "selisih timestamp buka-kirim. Rasio desimal 0-1 dibulatkan 4 angka. False negative tidak "
    "dihitung (menunggu OD-13)."
)


class MetrikDitahan(BaseModel):
    """Metrik yang sengaja belum dihitung beserta alasannya."""

    model_config = ConfigDict(frozen=True)

    kode: str = Field(description="Kode metrik yang ditahan.", examples=["false_negative"])
    alasan: str = Field(description="Alasan penahanan.", examples=["menunggu OD-13"])


def metrik_ditahan_bawaan() -> list[MetrikDitahan]:
    """Daftar konstan metrik ditahan: hanya `false_negative` (menunggu OD-13)."""
    return [MetrikDitahan(kode="false_negative", alasan="menunggu OD-13")]


class MetrikNarasiRead(BaseModel):
    """Metrik agregat alur narasi pada satu rentang tanggal."""

    model_config = ConfigDict(from_attributes=True)

    jumlah_keputusan: int = Field(ge=0, description="Jumlah keputusan Tim dalam rentang.")
    correction_rate: float | None = Field(
        default=None, description="TEAM_REVISE / jumlah_keputusan; null bila penyebut 0."
    )
    rejection_rate: float | None = Field(
        default=None, description="TEAM_REJECT / jumlah_keputusan; null bila penyebut 0."
    )
    source_coverage: float | None = Field(
        default=None, description="Proporsi versi bertautan sumber; null bila tak ada versi."
    )
    menit_aktif_total: int = Field(ge=0, description="Total menit aktif dalam rentang.")
    menit_aktif_median_per_kasus: float | None = Field(
        default=None, description="Median menit aktif per kasus (kasus ber-menit > 0)."
    )
    metrik_ditahan: list[MetrikDitahan] = Field(
        default_factory=metrik_ditahan_bawaan,
        description="Metrik yang belum dihitung (false negative menunggu OD-13).",
    )
