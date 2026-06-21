"""Skema Pydantic untuk seleksi relevansi Tahap 1."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TiSeleksiSubmit(BaseModel):
    """Payload submit seleksi relevansi Tahap 1: daftar kode task yang relevan."""

    model_config = ConfigDict(extra="forbid")

    task_kode: list[str] = Field(
        min_length=1,
        description="Daftar kode task yang relevan untuk responden ini (≥1).",
        examples=[["TIf0b59714", "TIa1b2c3d4"]],
    )


class TiSeleksiRead(BaseModel):
    """Representasi seleksi Tahap 1 satu responden."""

    model_config = ConfigDict(from_attributes=True)

    responden_id: str = Field(description="ID responden.", examples=["trsp_a1b2c3d4"])
    sesi_id: str = Field(description="ID sesi.", examples=["tises_a1b2c3d4"])
    task_kode: list[str] = Field(description="Daftar kode task yang dipilih relevan.")
    submitted_at: datetime | None = Field(default=None, description="Waktu submit.")
