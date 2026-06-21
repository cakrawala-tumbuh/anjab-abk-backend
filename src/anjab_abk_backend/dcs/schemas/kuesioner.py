"""Skema Pydantic untuk endpoint kuesioner partisipan (DCS)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DcsKuesionerItemRead(BaseModel):
    """Responden DCS diperkaya info sesi — dipakai endpoint /kuesioner/saya."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID responden.", examples=["drsp_a1b2c3d4"])
    sesi_id: str = Field(description="ID sesi DCS.", examples=["dses_a1b2c3d4"])
    jabatan_label: str = Field(description="Label jabatan responden.")
    sudah_submit: bool = Field(description="True jika jawaban sudah disubmit.")
    submitted_at: datetime | None = Field(default=None, description="Waktu submit.")
    created_at: datetime = Field(description="Waktu pendaftaran.")
    sesi_status: str = Field(
        description="Status sesi: DRAFT | OPEN | CLOSED | ANALYZED.", examples=["OPEN"]
    )
    sesi_periode: str = Field(description="Periode sesi (YYYY-MM).", examples=["2025-06"])
