"""Skema Pydantic untuk hasil analisis DCS."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DcsRiskFlag = Literal["HIGH", "MODERATE", "LOW"]


class DcsHasilSubSkalaRespondenRead(BaseModel):
    """Skor satu sub-skala untuk satu responden."""

    model_config = ConfigDict(from_attributes=True)

    subskala_kode: str = Field(description="Kode sub-skala.", examples=["DEMAND"])
    subskala_nama: str = Field(description="Nama sub-skala.", examples=["Demand (Tuntutan Kerja)"])
    skor: float = Field(description="Rata-rata 14 item setelah reverse UF.", examples=[3.71])


class DcsHasilRespondenRead(BaseModel):
    """Hasil analisis untuk satu responden (3 sub-skala)."""

    model_config = ConfigDict(from_attributes=True)

    responden_id: str = Field(description="ID responden.")
    sub_skala: list[DcsHasilSubSkalaRespondenRead] = Field(
        description="Skor per sub-skala (3 entri)."
    )
    risk_flag: DcsRiskFlag = Field(
        description="Flag risiko DCS responden ini.", examples=["MODERATE"]
    )


class DcsHasilSubSkalaSesiRead(BaseModel):
    """Hasil agregat satu sub-skala untuk satu sesi (seluruh responden)."""

    model_config = ConfigDict(from_attributes=True)

    subskala_kode: str = Field(description="Kode sub-skala.", examples=["DEMAND"])
    subskala_nama: str = Field(description="Nama sub-skala.", examples=["Demand (Tuntutan Kerja)"])
    n_responden: int = Field(description="Jumlah responden yang dianalisis.", examples=[7])
    skor_mean: float = Field(
        description="Rata-rata skor sub-skala antar responden.", examples=[3.71]
    )
    skor_std: float = Field(description="Standar deviasi skor sub-skala.", examples=[0.42])
    cronbach_alpha: float | None = Field(
        description="Cronbach's alpha (None jika responden < 2).", examples=[0.78]
    )


class DcsHasilSesiRead(BaseModel):
    """Hasil analisis lengkap satu sesi DCS (seluruh sub-skala + risk flag + K-Index)."""

    model_config = ConfigDict(from_attributes=True)

    sesi_id: str = Field(description="ID sesi.")
    periode: str = Field(description="Periode survei.")
    n_responden: int = Field(description="Total responden yang submit.")
    sub_skala: list[DcsHasilSubSkalaSesiRead] = Field(description="Hasil per sub-skala (3 entri).")
    risk_flag: DcsRiskFlag = Field(
        description=(
            "Flag risiko DCS: HIGH = demand tinggi + control/support rendah; "
            "MODERATE = salah satu kondisi; LOW = tidak ada kondisi."
        ),
        examples=["MODERATE"],
    )
    k_index: float | None = Field(
        default=None,
        description=(
            "K-Index psikososial (0–1). None jika wcp_sesi_id tidak disertakan. "
            "Rumus: 0,40×DemandPressure + 0,25×ControlDeficit + 0,25×SupportDeficit + 0,10×WCPRisk."
        ),
        examples=[0.42],
    )
    k_index_wcp_risk: float | None = Field(
        default=None,
        description="Komponen WCP risk yang dipakai dalam K-Index (0–1). None jika tidak ada.",
        examples=[0.65],
    )
