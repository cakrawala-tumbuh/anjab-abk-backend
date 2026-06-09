"""Skema Pydantic untuk resource `jenjang_pendidikan`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class JenjangPendidikanCreate(BaseModel):
    """Payload pembuatan jenjang pendidikan."""

    model_config = ConfigDict(extra="forbid")

    kode: str = Field(
        min_length=1,
        max_length=20,
        description="Kode jenjang (unik), mis. SD, SMP, SMA, SMK.",
        examples=["SD"],
    )
    nama: str = Field(
        min_length=1,
        max_length=100,
        description="Nama lengkap jenjang pendidikan.",
        examples=["Sekolah Dasar"],
    )
    urutan: int = Field(
        ge=0,
        default=0,
        description="Urutan tampilan (makin kecil makin atas).",
        examples=[3],
    )
    aktif: bool = Field(default=True, description="Status aktif jenjang.")


class JenjangPendidikanUpdate(BaseModel):
    """Payload pembaruan sebagian jenjang pendidikan."""

    model_config = ConfigDict(extra="forbid")

    kode: str | None = Field(default=None, min_length=1, max_length=20, description="Kode baru.")
    nama: str | None = Field(default=None, min_length=1, max_length=100, description="Nama baru.")
    urutan: int | None = Field(default=None, ge=0, description="Urutan baru.")
    aktif: bool | None = Field(default=None, description="Status aktif baru.")


class JenjangPendidikanRead(BaseModel):
    """Representasi jenjang pendidikan yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID unik jenjang pendidikan.", examples=["jp_a1b2c3d4"])
    kode: str = Field(description="Kode jenjang.", examples=["SD"])
    nama: str = Field(description="Nama lengkap.", examples=["Sekolah Dasar"])
    urutan: int = Field(description="Urutan tampilan.", examples=[3])
    aktif: bool = Field(description="Status aktif.")
