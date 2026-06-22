"""Skema Pydantic untuk endpoint kuesioner partisipan (Task Inventory)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TiKuesionerItemRead(BaseModel):
    """Responden Task Inventory diperkaya info sesi — dipakai /kuesioner/saya."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID responden.", examples=["trsp_a1b2c3d4"])
    sesi_id: str = Field(description="ID sesi Task Inventory.", examples=["tises_a1b2c3d4"])
    tahap1_submit: bool = Field(description="True jika seleksi Tahap 1 sudah disubmit.")
    tahap1_submitted_at: datetime | None = Field(default=None, description="Waktu submit Tahap 1.")
    tahap3_submit: bool = Field(description="True jika detail Tahap 3 sudah disubmit.")
    tahap3_submitted_at: datetime | None = Field(default=None, description="Waktu submit Tahap 3.")
    created_at: datetime = Field(description="Waktu pendaftaran.")
    sesi_status: str = Field(
        description="Status sesi: DRAFT | TAHAP1 | TAHAP2 | TAHAP3 | CLOSED | ANALYZED.",
        examples=["TAHAP1"],
    )
    sesi_jabatan_id: str = Field(
        description="ID jabatan yang dikaji dalam sesi.", examples=["jbt_a1b2c3d4"]
    )
    sesi_unit: str | None = Field(
        default=None, description="Unit/jenjang yang dikaji.", examples=["TK"]
    )
    sesi_periode: str = Field(description="Periode sesi (YYYY-MM).", examples=["2026-06"])
