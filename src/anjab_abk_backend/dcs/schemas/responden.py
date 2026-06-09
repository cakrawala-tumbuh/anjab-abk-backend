"""Skema Pydantic untuk resource `DcsResponden`."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DcsRespondenCreate(BaseModel):
    """Payload pendaftaran responden ke dalam sesi DCS."""

    model_config = ConfigDict(extra="forbid")

    nama: str | None = Field(
        default=None,
        max_length=200,
        description="Nama responden (opsional, boleh anonim).",
        examples=["Budi Santoso, S.Pd."],
    )
    jabatan_label: str = Field(
        min_length=1,
        max_length=200,
        description="Label jabatan responden (teks bebas).",
        examples=["Guru Matematika"],
    )


class DcsRespondenRead(BaseModel):
    """Representasi responden yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID responden.", examples=["drsp_a1b2c3d4"])
    sesi_id: str = Field(description="ID sesi induk.", examples=["dses_a1b2c3d4"])
    nama: str | None = Field(default=None, description="Nama responden.")
    jabatan_label: str = Field(description="Label jabatan responden.")
    sudah_submit: bool = Field(description="True jika jawaban sudah disubmit.")
    submitted_at: datetime | None = Field(default=None, description="Waktu submit jawaban.")
    created_at: datetime = Field(description="Waktu pendaftaran (UTC, ISO-8601).")
