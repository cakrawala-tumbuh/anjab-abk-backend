"""Skema Pydantic untuk resource `mata_pelajaran`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

KelompokMatpel = Literal["umum", "peminatan", "muatan_lokal", "kejuruan"]


class MataPelajaranCreate(BaseModel):
    """Payload pembuatan mata pelajaran."""

    model_config = ConfigDict(extra="forbid")

    kode: str = Field(
        min_length=1,
        max_length=20,
        description="Kode mata pelajaran (unik).",
        examples=["MTK"],
    )
    nama: str = Field(
        min_length=1,
        max_length=150,
        description="Nama mata pelajaran.",
        examples=["Matematika"],
    )
    kelompok: KelompokMatpel = Field(
        description="Kelompok mata pelajaran.",
        examples=["umum"],
    )
    deskripsi: str | None = Field(
        default=None,
        max_length=500,
        description="Deskripsi singkat.",
    )
    aktif: bool = Field(default=True, description="Status aktif mata pelajaran.")


class MataPelajaranUpdate(BaseModel):
    """Payload pembaruan sebagian mata pelajaran."""

    model_config = ConfigDict(extra="forbid")

    kode: str | None = Field(default=None, min_length=1, max_length=20, description="Kode baru.")
    nama: str | None = Field(default=None, min_length=1, max_length=150, description="Nama baru.")
    kelompok: KelompokMatpel | None = Field(default=None, description="Kelompok baru.")
    deskripsi: str | None = Field(default=None, max_length=500, description="Deskripsi baru.")
    aktif: bool | None = Field(default=None, description="Status aktif baru.")


class MataPelajaranRead(BaseModel):
    """Representasi mata pelajaran yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID unik mata pelajaran.", examples=["mp_a1b2c3d4"])
    kode: str = Field(description="Kode mata pelajaran.", examples=["MTK"])
    nama: str = Field(description="Nama mata pelajaran.", examples=["Matematika"])
    kelompok: KelompokMatpel = Field(description="Kelompok mata pelajaran.", examples=["umum"])
    deskripsi: str | None = Field(default=None, description="Deskripsi singkat.")
    aktif: bool = Field(description="Status aktif.")
