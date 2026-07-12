"""Skema Pydantic untuk resource `TsPenugasan`."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TsPenugasanCreate(BaseModel):
    """Payload penugasan Time Study ke seorang partisipan."""

    model_config = ConfigDict(extra="forbid")

    partisipan_id: str = Field(
        description="ID partisipan yang ditugaskan mencatat Time Study.",
        examples=["par_a1b2c3d4"],
    )
    aktif: bool = Field(default=True, description="Status aktif penugasan.")
    catatan: str | None = Field(
        default=None,
        max_length=500,
        description="Catatan opsional untuk penugasan ini.",
    )


class TsPenugasanBulkCreate(BaseModel):
    """Payload penugasan Time Study massal (bulk) ke banyak partisipan sekaligus."""

    model_config = ConfigDict(extra="forbid")

    partisipan_ids: list[str] = Field(
        min_length=1,
        description="Daftar ID partisipan yang ditugaskan mencatat Time Study.",
        examples=[["par_a1b2c3d4", "par_e5f6g7h8"]],
    )
    aktif: bool = Field(default=True, description="Status aktif penugasan.")
    catatan: str | None = Field(
        default=None,
        max_length=500,
        description="Catatan opsional, diterapkan ke seluruh baris dalam batch ini.",
    )


class TsPenugasanUpdate(BaseModel):
    """Payload pembaruan penugasan Time Study (mis. toggle aktif)."""

    model_config = ConfigDict(extra="forbid")

    aktif: bool | None = Field(default=None, description="Status aktif penugasan.")
    catatan: str | None = Field(default=None, max_length=500, description="Catatan baru.")


class TsPenugasanRead(BaseModel):
    """Representasi penugasan Time Study yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID penugasan.", examples=["tpn_a1b2c3d4"])
    partisipan_id: str = Field(description="ID partisipan yang ditugaskan.")
    aktif: bool = Field(description="Status aktif penugasan.")
    catatan: str | None = Field(default=None, description="Catatan.")
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
