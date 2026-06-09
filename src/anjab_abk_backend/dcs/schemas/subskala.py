"""Skema Pydantic untuk sub-skala dan item DCS (master data, read-only)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ArahItem = Literal["F", "UF"]


class DcsItemRead(BaseModel):
    """Representasi satu item pernyataan DCS."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID item.", examples=["ditm_D1a"])
    item_id: str = Field(description="Kode item orisinal.", examples=["D1a"])
    subskala_kode: str = Field(description="Kode sub-skala.", examples=["DEMAND"])
    sub_dimensi: str = Field(description="Sub-dimensi item.", examples=["Volume"])
    pernyataan: str = Field(
        description="Teks pernyataan.",
        examples=["Saya harus menyelesaikan banyak tugas dalam waktu yang sangat terbatas."],
    )
    arah: ArahItem = Field(
        description="Arah item: F (Favorable) atau UF (Unfavorable, reverse-scored).",
        examples=["UF"],
    )
    urutan: int = Field(description="Urutan global item (1–42).", examples=[1])


class DcsSubSkalaRead(BaseModel):
    """Representasi sub-skala DCS tanpa item."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID sub-skala.", examples=["dsk_DEMAND"])
    kode: str = Field(description="Kode sub-skala.", examples=["DEMAND"])
    nama: str = Field(description="Nama sub-skala.", examples=["Demand (Tuntutan Kerja)"])
    urutan: int = Field(description="Urutan sub-skala (1–3).", examples=[1])


class DcsSubSkalaWithItemsRead(DcsSubSkalaRead):
    """Representasi sub-skala DCS beserta 14 item-nya."""

    items: list[DcsItemRead] = Field(description="Daftar 14 item sub-skala ini.")
