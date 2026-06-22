"""Skema Pydantic untuk resource `TugasPokok` (master data catalog TI).

TugasPokok adalah klaster tugas tingkat pertama. Setiap TugasPokok melekat pada
satu Jabatan (via jabatan_id) sehingga jabatan diwariskan ke DetilTugas dan
UraianTugas melalui relasi M2O.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TugasPokokCreate(BaseModel):
    """Payload pembuatan tugas pokok."""

    model_config = ConfigDict(extra="forbid")

    jabatan_id: str = Field(
        min_length=1,
        description="ID jabatan yang menjadi induk tugas pokok ini.",
        examples=["jbt_a1b2c3d4"],
    )
    nama: str = Field(
        min_length=1,
        max_length=300,
        description="Nama tugas pokok (klaster tugas).",
        examples=["Pengelolaan SDM"],
    )


class TugasPokokUpdate(BaseModel):
    """Payload pembaruan sebagian tugas pokok."""

    model_config = ConfigDict(extra="forbid")

    jabatan_id: str | None = Field(
        default=None,
        min_length=1,
        description="ID jabatan baru.",
    )
    nama: str | None = Field(
        default=None,
        min_length=1,
        max_length=300,
        description="Nama baru.",
    )


class TugasPokokRead(BaseModel):
    """Representasi tugas pokok yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID unik tugas pokok.", examples=["tp_a1b2c3d4"])
    jabatan_id: str = Field(description="ID jabatan induk.", examples=["jbt_a1b2c3d4"])
    nama: str = Field(description="Nama tugas pokok.", examples=["Pengelolaan SDM"])
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
