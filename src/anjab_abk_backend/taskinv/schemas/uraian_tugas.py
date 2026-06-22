"""Skema Pydantic untuk resource `UraianTugas` (master data catalog TI).

UraianTugas adalah pernyataan tugas spesifik (task statement) level terbawah.
Relasi M2O: UraianTugas → TugasPokok (via tugas_pokok_id) dan
           UraianTugas → DetilTugas (via detil_tugas_id).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UraianTugasCreate(BaseModel):
    """Payload pembuatan uraian tugas."""

    model_config = ConfigDict(extra="forbid")

    kode: str = Field(
        min_length=1,
        max_length=20,
        description="Kode task deterministik (unik).",
        examples=["TIf0b59714"],
    )
    uraian: str = Field(
        min_length=1,
        max_length=500,
        description="Pernyataan tugas (task statement).",
        examples=["Menyusun evaluasi karyawan"],
    )
    unit: str = Field(
        min_length=1,
        max_length=20,
        description="Unit/jenjang (TK, SD, SMP, SMA, SMK, dll.).",
        examples=["TK"],
    )
    kategori_jabatan: str = Field(
        min_length=1,
        max_length=200,
        description="Kategori jabatan.",
        examples=["Kepala Sekolah"],
    )
    urutan: int = Field(
        ge=1,
        description="Urutan dalam kombinasi unit × kategori jabatan.",
        examples=[1],
    )
    detil_tugas_id: str | None = Field(
        default=None,
        description="ID detil tugas induk (M2O). Null jika task tidak masuk detil tugas.",
        examples=["dt_a1b2c3d4"],
    )
    tugas_pokok_id: str = Field(
        description="ID tugas pokok induk (M2O, denormalisasi untuk efisiensi query).",
        examples=["tp_a1b2c3d4"],
    )


class UraianTugasUpdate(BaseModel):
    """Payload pembaruan sebagian uraian tugas."""

    model_config = ConfigDict(extra="forbid")

    kode: str | None = Field(default=None, min_length=1, max_length=20, description="Kode baru.")
    uraian: str | None = Field(
        default=None, min_length=1, max_length=500, description="Pernyataan tugas baru."
    )
    unit: str | None = Field(default=None, min_length=1, max_length=20, description="Unit baru.")
    kategori_jabatan: str | None = Field(
        default=None, min_length=1, max_length=200, description="Kategori jabatan baru."
    )
    urutan: int | None = Field(default=None, ge=1, description="Urutan baru.")
    detil_tugas_id: str | None = Field(default=None, description="ID detil tugas induk baru.")
    tugas_pokok_id: str | None = Field(default=None, description="ID tugas pokok induk baru.")


class UraianTugasRead(BaseModel):
    """Representasi uraian tugas yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID unik uraian tugas.", examples=["ut_a1b2c3d4"])
    kode: str = Field(description="Kode task deterministik.", examples=["TIf0b59714"])
    uraian: str = Field(
        description="Pernyataan tugas (task statement).", examples=["Menyusun evaluasi karyawan"]
    )
    unit: str = Field(description="Unit/jenjang.", examples=["TK"])
    kategori_jabatan: str = Field(description="Kategori jabatan.", examples=["Kepala Sekolah"])
    urutan: int = Field(description="Urutan dalam kombinasi unit × kategori jabatan.", examples=[1])
    detil_tugas_id: str | None = Field(
        default=None, description="ID detil tugas induk.", examples=["dt_a1b2c3d4"]
    )
    tugas_pokok_id: str = Field(description="ID tugas pokok induk.", examples=["tp_a1b2c3d4"])
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
