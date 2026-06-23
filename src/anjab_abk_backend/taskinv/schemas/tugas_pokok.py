"""Skema Pydantic untuk resource `TugasPokok` (master data catalog TI).

TugasPokok adalah klaster tugas tingkat pertama. Setiap TugasPokok memiliki
relasi M2M ke Jabatan (via jabatan_ids). DetilTugas hanya dapat dipilihkan
jabatan yang merupakan subset dari jabatan_ids TugasPokok induknya.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TugasPokokCreate(BaseModel):
    """Payload pembuatan tugas pokok."""

    model_config = ConfigDict(extra="forbid")

    jabatan_ids: list[str] = Field(
        min_length=1,
        description="Daftar ID jabatan yang terkait dengan tugas pokok ini (M2M, minimal 1).",
        examples=[["jbt_a1b2c3d4", "jbt_b2c3d4e5"]],
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

    jabatan_ids: list[str] | None = Field(
        default=None,
        min_length=1,
        description="Daftar ID jabatan baru (M2M, minimal 1 item bila diisi).",
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
    jabatan_ids: list[str] = Field(
        description="Daftar ID jabatan terkait (M2M).",
        examples=[["jbt_a1b2c3d4"]],
    )
    nama: str = Field(description="Nama tugas pokok.", examples=["Pengelolaan SDM"])
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
