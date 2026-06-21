"""Skema Pydantic untuk resource `sme_panel` (ANJAB)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SMEPanelCreate(BaseModel):
    """Payload pembuatan SME panel."""

    model_config = ConfigDict(extra="forbid")

    jabatan_id: str = Field(
        description="ID jabatan yang menjadi dasar panel SME ini.",
        examples=["jbt_a1b2c3d4"],
    )
    aktif: bool = Field(default=True, description="Status aktif panel.")


class SMEPanelUpdate(BaseModel):
    """Payload pembaruan sebagian SME panel."""

    model_config = ConfigDict(extra="forbid")

    aktif: bool | None = Field(default=None, description="Status aktif baru.")


class SMEPanelRead(BaseModel):
    """Representasi SME panel yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID unik SME panel.", examples=["sme_a1b2c3d4"])
    jabatan_id: str = Field(description="ID jabatan yang menjadi dasar panel ini.")
    partisipan_ids: list[str] = Field(
        default_factory=list,
        description="Daftar ID partisipan anggota panel.",
    )
    aktif: bool = Field(description="Status aktif.")
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")


class SMEPanelAnggotaAdd(BaseModel):
    """Payload penambahan anggota ke SME panel."""

    model_config = ConfigDict(extra="forbid")

    partisipan_id: str = Field(
        description="ID partisipan yang akan ditambahkan ke panel.",
        examples=["par_a1b2c3d4"],
    )
