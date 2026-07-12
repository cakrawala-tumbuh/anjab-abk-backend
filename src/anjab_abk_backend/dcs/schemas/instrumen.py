"""Skema Pydantic untuk instrumen singleton `DcsInstrumen`."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StatusInstrumenDcs = Literal["OPEN", "CLOSED", "ANALYZED"]


class DcsInstrumenUpdate(BaseModel):
    """Payload pembaruan parsial instrumen DCS (min_responden/catatan)."""

    model_config = ConfigDict(extra="forbid")

    min_responden: int | None = Field(
        default=None, ge=1, description="Jumlah minimum responden baru (cutoff analisis)."
    )
    catatan: str | None = Field(default=None, max_length=500, description="Catatan baru.")


class DcsInstrumenRead(BaseModel):
    """Representasi instrumen DCS (satu baris tetap, `id='dcs'`)."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID instrumen (selalu 'dcs').", examples=["dcs"])
    status: StatusInstrumenDcs = Field(description="Status instrumen.", examples=["OPEN"])
    min_responden: int = Field(description="Jumlah minimum responden (cutoff analisis).")
    catatan: str | None = Field(default=None, description="Catatan.")
    closed_at: datetime | None = Field(
        default=None, description="Waktu instrumen terakhir ditutup (None bila belum pernah)."
    )
    created_at: datetime = Field(description="Waktu baris instrumen dibuat (oleh migrasi).")
