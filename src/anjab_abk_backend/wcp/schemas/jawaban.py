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


class WcpJawabanUpsert(BaseModel):
    """Payload draft-save (upsert parsial) jawaban untuk satu responden.

    Boleh 0..72 item; tiap item di-upsert per `item_id`. Kelengkapan 72 item
    divalidasi terpisah saat finalisasi (`POST .../jawaban/submit`).
    """

    model_config = ConfigDict(extra="forbid")

    jawaban: list[WcpJawabanItem] = Field(
        max_length=72,
        description="0..72 jawaban parsial, satu per item WCP.",
    )


class WcpJawabanRead(BaseModel):
    """Representasi satu jawaban yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID jawaban.", examples=["wjwb_a1b2c3d4"])
    responden_id: str = Field(description="ID responden.", examples=["wrsp_a1b2c3d4"])
    item_id: str = Field(description="Kode item orisinal.", examples=["SC1a"])
    skor_raw: int = Field(description="Skor mentah 1–5.")
