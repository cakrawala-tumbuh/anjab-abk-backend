"""Skema Pydantic untuk resource `TiResponden`."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TiRespondenCreate(BaseModel):
    """Payload pendaftaran responden ke sesi Task Inventory."""

    model_config = ConfigDict(extra="forbid")

    nama: str | None = Field(
        default=None,
        max_length=200,
        description="Nama responden (opsional, boleh anonim).",
        examples=["Budi Santoso, S.Pd."],
    )
    partisipan_id: str | None = Field(
        default=None,
        description="ID partisipan terhubung (opsional, untuk fitur 'Kuesioner Saya').",
        examples=["p_a1b2c3d4"],
    )


class TiRespondenRead(BaseModel):
    """Representasi responden yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID responden.", examples=["trsp_a1b2c3d4"])
    sesi_id: str = Field(description="ID sesi induk.", examples=["tises_a1b2c3d4"])
    nama: str | None = Field(default=None, description="Nama responden.")
    partisipan_id: str | None = Field(default=None, description="ID partisipan terhubung.")
    tahap1_submit: bool = Field(description="True jika seleksi Tahap 1 sudah disubmit.")
    tahap1_submitted_at: datetime | None = Field(default=None, description="Waktu submit Tahap 1.")
    tahap2_submit: bool = Field(description="True jika detail Tahap 2 sudah disubmit.")
    tahap2_submitted_at: datetime | None = Field(default=None, description="Waktu submit Tahap 2.")
    created_at: datetime = Field(description="Waktu pendaftaran (UTC, ISO-8601).")
