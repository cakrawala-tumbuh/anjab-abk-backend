"""Skema Pydantic untuk resource `DcsJawaban`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DcsJawabanItem(BaseModel):
    """Satu jawaban item dalam bulk submission."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(
        description="Kode item orisinal (mis. D1a).",
        examples=["D1a"],
    )
    skor_raw: int = Field(
        ge=1,
        le=5,
        description="Skor mentah 1–5 dari responden.",
        examples=[4],
    )


class DcsJawabanBulkCreate(BaseModel):
    """Payload bulk submission 42 jawaban untuk satu responden."""

    model_config = ConfigDict(extra="forbid")

    jawaban: list[DcsJawabanItem] = Field(
        min_length=42,
        max_length=42,
        description="Tepat 42 jawaban, satu per item DCS.",
    )


class DcsJawabanRead(BaseModel):
    """Representasi satu jawaban yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID jawaban.", examples=["djwb_a1b2c3d4"])
    responden_id: str = Field(description="ID responden.", examples=["drsp_a1b2c3d4"])
    item_id: str = Field(description="Kode item orisinal.", examples=["D1a"])
    skor_raw: int = Field(description="Skor mentah 1–5.")
