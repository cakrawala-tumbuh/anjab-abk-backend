"""Skema Pydantic untuk resource `TsSesi`."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StatusSesi = Literal["DRAFT", "OPEN", "CLOSED", "ANALYZED"]


class TsSesiCreate(BaseModel):
    """Payload pembuatan sesi Time Study."""

    model_config = ConfigDict(extra="forbid")

    jabatan_id: str = Field(
        description="ID jabatan yang dikaji.",
        examples=["jbt_a1b2c3d4"],
    )
    periode: str = Field(
        min_length=7,
        max_length=7,
        pattern=r"^\d{4}-\d{2}$",
        description="Periode survei format YYYY-MM.",
        examples=["2025-06"],
    )
    catatan: str | None = Field(
        default=None,
        max_length=500,
        description="Catatan opsional untuk sesi ini.",
    )


class TsSesiUpdate(BaseModel):
    """Payload pembaruan sesi Time Study (hanya saat DRAFT)."""

    model_config = ConfigDict(extra="forbid")

    periode: str | None = Field(
        default=None,
        min_length=7,
        max_length=7,
        pattern=r"^\d{4}-\d{2}$",
        description="Periode baru.",
    )
    catatan: str | None = Field(default=None, max_length=500, description="Catatan baru.")


class TsSesiRead(BaseModel):
    """Representasi sesi Time Study yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID sesi.", examples=["tses_a1b2c3d4"])
    jabatan_id: str = Field(description="ID jabatan.", examples=["jbt_a1b2c3d4"])
    periode: str = Field(description="Periode survei (YYYY-MM).", examples=["2025-06"])
    status: StatusSesi = Field(description="Status sesi.", examples=["DRAFT"])
    catatan: str | None = Field(default=None, description="Catatan.")
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
