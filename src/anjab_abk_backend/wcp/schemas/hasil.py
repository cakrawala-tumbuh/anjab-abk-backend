"""Skema Pydantic untuk hasil analisis WCP."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from ...schemas.common import HasilRawItemRead

InterpretasiNormal = Literal["BAIK", "CUKUP", "PERLU_PERHATIAN"]
InterpretasiRisiko = Literal["AMAN", "WASPADA", "RISIKO_TINGGI"]
Interpretasi = Literal["BAIK", "CUKUP", "PERLU_PERHATIAN", "AMAN", "WASPADA", "RISIKO_TINGGI"]


class WcpHasilDimensiRespondenRead(BaseModel):
    """Skor satu dimensi untuk satu responden."""

    model_config = ConfigDict(from_attributes=True)

    dimensi_kode: str = Field(description="Kode dimensi.", examples=["SC"])
    dimensi_nama: str = Field(description="Nama dimensi.", examples=["Stability of Change"])
    is_risk: bool = Field(description="True jika dimensi risiko.")
    skor: float = Field(description="Rata-rata 6 item setelah reverse scoring.", examples=[3.83])
    interpretasi: Interpretasi = Field(description="Interpretasi skor.", examples=["CUKUP"])


class WcpHasilRespondenRead(BaseModel):
    """Hasil analisis untuk satu responden (12 dimensi)."""

    model_config = ConfigDict(from_attributes=True)

    responden_id: str = Field(description="ID responden.")
    dimensi: list[WcpHasilDimensiRespondenRead] = Field(description="Skor per dimensi (12 entri).")


class WcpHasilDimensiRead(BaseModel):
    """Hasil agregat satu dimensi (seluruh responden ber-submit instrumen WCP)."""

    model_config = ConfigDict(from_attributes=True)

    dimensi_kode: str = Field(description="Kode dimensi.", examples=["SC"])
    dimensi_nama: str = Field(description="Nama dimensi.", examples=["Stability of Change"])
    is_risk: bool = Field(description="True jika dimensi risiko.")
    n_responden: int = Field(description="Jumlah responden yang dianalisis.", examples=[7])
    skor_mean: float = Field(description="Rata-rata skor dimensi antar responden.", examples=[3.71])
    skor_std: float = Field(description="Standar deviasi skor dimensi.", examples=[0.42])
    cronbach_alpha: float | None = Field(
        description="Cronbach's alpha (None jika responden < 2).", examples=[0.78]
    )
    interpretasi: Interpretasi = Field(description="Interpretasi skor.", examples=["CUKUP"])


class WcpHasilRead(BaseModel):
    """Hasil analisis lengkap instrumen WCP (seluruh dimensi)."""

    model_config = ConfigDict(from_attributes=True)

    mode: Literal["SCORED"] = Field(
        default="SCORED", description="Diskriminan: skor aktif (flag WCP_DCS_SCORING hidup)."
    )
    n_responden: int = Field(description="Total responden yang submit.")
    dimensi: list[WcpHasilDimensiRead] = Field(description="Hasil per dimensi (12 entri).")


class WcpHasilRawRead(BaseModel):
    """Hasil WCP mode `RAW_ONLY`: raw per item + statistik deskriptif raw, tanpa skor."""

    mode: Literal["RAW_ONLY"] = Field(
        default="RAW_ONLY", description="Diskriminan: skoring dimatikan (flag mati)."
    )
    n_responden: int = Field(description="Total responden yang submit.")
    items: list[HasilRawItemRead] = Field(description="Agregat raw per item.")


WcpHasilResponse = Annotated[WcpHasilRead | WcpHasilRawRead, Field(discriminator="mode")]
"""Union diskriminan hasil WCP (`mode`: `SCORED` | `RAW_ONLY`)."""
