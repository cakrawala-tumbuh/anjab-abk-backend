"""Skema Pydantic untuk dimensi dan item WCP (master data, read-only)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WcpItemRead(BaseModel):
    """Representasi satu item pernyataan WCP."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID item.", examples=["witm_SC1a"])
    item_id: str = Field(description="Kode item orisinal.", examples=["SC1a"])
    dimensi_kode: str = Field(description="Kode dimensi.", examples=["SC"])
    indikator_kode: str = Field(description="Kode indikator (1/2/3).", examples=["1"])
    indikator_label: str = Field(
        description="Label indikator.", examples=["Frekuensi perubahan kebijakan"]
    )
    pernyataan: str = Field(
        description="Teks pernyataan.",
        examples=["Kebijakan dan prosedur kerja di unit saya berubah terlalu sering."],
    )
    reverse_type: str = Field(
        description="Tipe scoring: NONE | R | UF | R_STAR.",
        examples=["R"],
    )
    urutan: int = Field(description="Urutan global item (1–72).", examples=[1])


class WcpDimensiRead(BaseModel):
    """Representasi dimensi WCP tanpa item."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID dimensi.", examples=["wdim_SC"])
    kode: str = Field(description="Kode dimensi.", examples=["SC"])
    nama: str = Field(description="Nama dimensi.", examples=["Stability of Change"])
    urutan: int = Field(description="Urutan dimensi (1–12).", examples=[1])
    is_risk: bool = Field(
        description="True jika dimensi risiko (CH/SD/PI); skor tinggi = risiko tinggi."
    )


class WcpDimensiWithItemsRead(WcpDimensiRead):
    """Representasi dimensi WCP beserta 6 item-nya."""

    items: list[WcpItemRead] = Field(description="Daftar 6 item dimensi ini.")
