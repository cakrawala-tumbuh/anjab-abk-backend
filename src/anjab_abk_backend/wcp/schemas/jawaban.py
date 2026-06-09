"""Skema Pydantic untuk resource `WcpJawaban`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WcpJawabanItem(BaseModel):
    """Satu jawaban item dalam bulk submission."""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(
        description="Kode item orisinal (mis. SC1a).",
        examples=["SC1a"],
    )
    skor_raw: int = Field(
        ge=1,
        le=5,
        description="Skor mentah 1–5 dari responden.",
        examples=[4],
    )


class WcpJawabanBulkCreate(BaseModel):
    """Payload bulk submission 72 jawaban untuk satu responden."""

    model_config = ConfigDict(extra="forbid")

    jawaban: list[WcpJawabanItem] = Field(
        min_length=72,
        max_length=72,
        description="Tepat 72 jawaban, satu per item WCP.",
    )


class WcpJawabanRead(BaseModel):
    """Representasi satu jawaban yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID jawaban.", examples=["wjwb_a1b2c3d4"])
    responden_id: str = Field(description="ID responden.", examples=["wrsp_a1b2c3d4"])
    item_id: str = Field(description="Kode item orisinal.", examples=["SC1a"])
    skor_raw: int = Field(description="Skor mentah 1–5.")
