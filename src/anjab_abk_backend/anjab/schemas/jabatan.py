"""Skema Pydantic untuk resource `jabatan` (ANJAB)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

JenisJabatan = Literal["struktural", "fungsional", "teknisi"]


class JabatanCreate(BaseModel):
    """Payload pembuatan jabatan."""

    model_config = ConfigDict(extra="forbid")

    kode: str = Field(
        min_length=1,
        max_length=30,
        description="Kode jabatan (unik).",
        examples=["KS-001"],
    )
    nama: str = Field(
        min_length=1,
        max_length=200,
        description="Nama jabatan.",
        examples=["Kepala Sekolah"],
    )
    jenis: JenisJabatan = Field(
        description="Jenis jabatan.",
        examples=["struktural"],
    )
    unit_kerja_id: str | None = Field(
        default=None,
        description="ID unit kerja / sekolah tempat jabatan ini berada.",
        examples=["skl_a1b2c3d4"],
    )
    deskripsi: str | None = Field(
        default=None,
        max_length=1000,
        description="Deskripsi singkat jabatan.",
    )
    aktif: bool = Field(default=True, description="Status aktif jabatan.")


class JabatanUpdate(BaseModel):
    """Payload pembaruan sebagian jabatan."""

    model_config = ConfigDict(extra="forbid")

    kode: str | None = Field(default=None, min_length=1, max_length=30, description="Kode baru.")
    nama: str | None = Field(default=None, min_length=1, max_length=200, description="Nama baru.")
    jenis: JenisJabatan | None = Field(default=None, description="Jenis baru.")
    unit_kerja_id: str | None = Field(default=None, description="ID unit kerja baru.")
    deskripsi: str | None = Field(default=None, max_length=1000, description="Deskripsi baru.")
    aktif: bool | None = Field(default=None, description="Status aktif baru.")


class JabatanRead(BaseModel):
    """Representasi jabatan yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID unik jabatan.", examples=["jbt_a1b2c3d4"])
    kode: str = Field(description="Kode jabatan.", examples=["KS-001"])
    nama: str = Field(description="Nama jabatan.", examples=["Kepala Sekolah"])
    jenis: JenisJabatan = Field(description="Jenis jabatan.", examples=["struktural"])
    unit_kerja_id: str | None = Field(default=None, description="ID unit kerja.")
    deskripsi: str | None = Field(default=None, description="Deskripsi jabatan.")
    aktif: bool = Field(description="Status aktif.")
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
