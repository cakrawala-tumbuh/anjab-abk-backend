"""Skema Pydantic untuk resource `partisipan`."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PartisipanCreate(BaseModel):
    """Payload pembuatan partisipan."""

    model_config = ConfigDict(extra="forbid")

    nama: str = Field(
        min_length=1,
        max_length=200,
        description="Nama lengkap partisipan.",
        examples=["Siti Rahayu, S.Pd."],
    )
    sekolah_id: str = Field(
        description="ID sekolah / satuan pendidikan tempat partisipan bertugas.",
        examples=["skl_a1b2c3d4"],
    )
    jabatan_utama_id: str = Field(
        description="ID jabatan utama partisipan.",
        examples=["jbt_a1b2c3d4"],
    )
    jabatan_tambahan_ids: list[str] = Field(
        default_factory=list,
        description="Daftar ID jabatan tambahan (boleh kosong).",
        examples=[["jbt_b2c3d4e5", "jbt_c3d4e5f6"]],
    )
    masa_kerja_tahun: int = Field(
        ge=0,
        description="Masa kerja dalam tahun.",
        examples=[5],
    )
    masa_kerja_bulan: int = Field(
        default=0,
        ge=0,
        le=11,
        description="Sisa masa kerja dalam bulan (0–11).",
        examples=[3],
    )
    mata_pelajaran_utama_id: str | None = Field(
        default=None,
        description="ID mata pelajaran utama (opsional, relevan untuk guru).",
        examples=["mp_a1b2c3d4"],
    )
    aktif: bool = Field(default=True, description="Status aktif partisipan.")


class PartisipanUpdate(BaseModel):
    """Payload pembaruan sebagian partisipan."""

    model_config = ConfigDict(extra="forbid")

    nama: str | None = Field(default=None, min_length=1, max_length=200, description="Nama baru.")
    sekolah_id: str | None = Field(default=None, description="ID sekolah baru.")
    jabatan_utama_id: str | None = Field(default=None, description="ID jabatan utama baru.")
    jabatan_tambahan_ids: list[str] | None = Field(
        default=None, description="Daftar ID jabatan tambahan baru (menggantikan seluruhnya)."
    )
    masa_kerja_tahun: int | None = Field(default=None, ge=0, description="Masa kerja tahun baru.")
    masa_kerja_bulan: int | None = Field(
        default=None, ge=0, le=11, description="Masa kerja bulan baru (0–11)."
    )
    mata_pelajaran_utama_id: str | None = Field(
        default=None, description="ID mata pelajaran utama baru."
    )
    aktif: bool | None = Field(default=None, description="Status aktif baru.")


class PartisipanRead(BaseModel):
    """Representasi partisipan yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID unik partisipan.", examples=["par_a1b2c3d4"])
    nama: str = Field(description="Nama lengkap partisipan.", examples=["Siti Rahayu, S.Pd."])
    sekolah_id: str = Field(description="ID sekolah tempat bertugas.")
    jabatan_utama_id: str = Field(description="ID jabatan utama.")
    jabatan_tambahan_ids: list[str] = Field(description="Daftar ID jabatan tambahan.")
    masa_kerja_tahun: int = Field(description="Masa kerja dalam tahun.")
    masa_kerja_bulan: int = Field(description="Sisa masa kerja dalam bulan (0–11).")
    mata_pelajaran_utama_id: str | None = Field(
        default=None, description="ID mata pelajaran utama (opsional)."
    )
    aktif: bool = Field(description="Status aktif.")
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
