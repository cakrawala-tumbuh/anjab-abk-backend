"""Skema Pydantic untuk resource `DetilTugas` (master data catalog TI)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DetilTugasCreate(BaseModel):
    """Payload pembuatan detil tugas."""

    model_config = ConfigDict(extra="forbid")

    nama: str = Field(
        min_length=1,
        max_length=300,
        description="Nama detil tugas (kelompok tugas).",
        examples=["Mengevaluasi Kinerja Karyawan"],
    )
    tugas_pokok_id: str = Field(
        description="ID tugas pokok induk.",
        examples=["tp_a1b2c3d4"],
    )


class DetilTugasUpdate(BaseModel):
    """Payload pembaruan sebagian detil tugas."""

    model_config = ConfigDict(extra="forbid")

    nama: str | None = Field(
        default=None,
        min_length=1,
        max_length=300,
        description="Nama baru.",
    )
    tugas_pokok_id: str | None = Field(
        default=None,
        description="ID tugas pokok induk baru.",
    )


class DetilTugasRead(BaseModel):
    """Representasi detil tugas yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID unik detil tugas.", examples=["dt_a1b2c3d4"])
    nama: str = Field(description="Nama detil tugas.", examples=["Mengevaluasi Kinerja Karyawan"])
    tugas_pokok_id: str = Field(description="ID tugas pokok induk.", examples=["tp_a1b2c3d4"])
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
