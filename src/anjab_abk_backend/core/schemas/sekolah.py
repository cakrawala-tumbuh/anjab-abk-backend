"""Skema Pydantic untuk resource `sekolah`."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SekolahCreate(BaseModel):
    """Payload pembuatan sekolah / satuan pendidikan."""

    model_config = ConfigDict(extra="forbid")

    nama: str = Field(
        min_length=1,
        max_length=200,
        description="Nama sekolah.",
        examples=["SD Negeri 1 Bandung"],
    )
    npsn: str | None = Field(
        default=None,
        min_length=8,
        max_length=8,
        pattern=r"^\d{8}$",
        description="Nomor Pokok Sekolah Nasional (8 digit angka).",
        examples=["20201234"],
    )
    jenjang_pendidikan_id: str = Field(
        description="ID jenjang pendidikan.",
        examples=["jp_a1b2c3d4"],
    )
    kota: str | None = Field(
        default=None,
        max_length=100,
        description="Kota lokasi sekolah.",
        examples=["Bandung"],
    )
    provinsi: str | None = Field(
        default=None,
        max_length=100,
        description="Provinsi lokasi sekolah.",
        examples=["Jawa Barat"],
    )
    aktif: bool = Field(default=True, description="Status aktif sekolah.")


class SekolahUpdate(BaseModel):
    """Payload pembaruan sebagian sekolah."""

    model_config = ConfigDict(extra="forbid")

    nama: str | None = Field(default=None, min_length=1, max_length=200, description="Nama baru.")
    npsn: str | None = Field(
        default=None,
        min_length=8,
        max_length=8,
        pattern=r"^\d{8}$",
        description="NPSN baru.",
    )
    jenjang_pendidikan_id: str | None = Field(
        default=None, description="ID jenjang pendidikan baru."
    )
    kota: str | None = Field(default=None, max_length=100, description="Kota baru.")
    provinsi: str | None = Field(default=None, max_length=100, description="Provinsi baru.")
    aktif: bool | None = Field(default=None, description="Status aktif baru.")


class SekolahRead(BaseModel):
    """Representasi sekolah yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID unik sekolah.", examples=["skl_a1b2c3d4"])
    nama: str = Field(description="Nama sekolah.", examples=["SD Negeri 1 Bandung"])
    npsn: str | None = Field(default=None, description="Nomor Pokok Sekolah Nasional.")
    jenjang_pendidikan_id: str = Field(description="ID jenjang pendidikan.")
    kota: str | None = Field(default=None, description="Kota.")
    provinsi: str | None = Field(default=None, description="Provinsi.")
    aktif: bool = Field(description="Status aktif.")
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
