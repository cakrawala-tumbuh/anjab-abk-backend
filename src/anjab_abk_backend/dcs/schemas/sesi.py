"""Skema Pydantic untuk resource `DcsSesi`."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StatusSesiDcs = Literal["DRAFT", "OPEN", "CLOSED", "ANALYZED"]


class DcsSesiCreate(BaseModel):
    """Payload pembuatan sesi DCS."""

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
    min_responden: int = Field(
        default=6,
        ge=1,
        description="Jumlah minimum responden.",
        examples=[6],
    )
    max_responden: int = Field(
        default=8,
        ge=1,
        description="Jumlah maksimum responden.",
        examples=[8],
    )
    catatan: str | None = Field(
        default=None,
        max_length=500,
        description="Catatan opsional untuk sesi ini.",
    )


class DcsSesiUpdate(BaseModel):
    """Payload pembaruan sesi DCS (hanya saat DRAFT)."""

    model_config = ConfigDict(extra="forbid")

    periode: str | None = Field(
        default=None,
        min_length=7,
        max_length=7,
        pattern=r"^\d{4}-\d{2}$",
        description="Periode baru.",
    )
    min_responden: int | None = Field(default=None, ge=1, description="Minimum responden baru.")
    max_responden: int | None = Field(default=None, ge=1, description="Maksimum responden baru.")
    catatan: str | None = Field(default=None, max_length=500, description="Catatan baru.")


class DcsSesiRead(BaseModel):
    """Representasi sesi DCS yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID sesi.", examples=["dses_a1b2c3d4"])
    jabatan_id: str = Field(description="ID jabatan.", examples=["jbt_a1b2c3d4"])
    periode: str = Field(description="Periode survei (YYYY-MM).", examples=["2025-06"])
    status: StatusSesiDcs = Field(description="Status sesi.", examples=["DRAFT"])
    min_responden: int = Field(description="Minimum responden.")
    max_responden: int = Field(description="Maksimum responden.")
    catatan: str | None = Field(default=None, description="Catatan.")
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
