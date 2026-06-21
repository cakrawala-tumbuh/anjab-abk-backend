"""Skema Pydantic untuk endpoint kuesioner partisipan (Time Study)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TsKuesionerItemRead(BaseModel):
    """Responden TS diperkaya info sesi — dipakai endpoint /kuesioner/saya."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID responden.", examples=["trsp_a1b2c3d4"])
    sesi_id: str = Field(description="ID sesi Time Study.", examples=["tses_a1b2c3d4"])
    jabatan_label: str = Field(description="Label jabatan responden.")
    created_at: datetime = Field(description="Waktu pendaftaran.")
    sesi_status: str = Field(
        description="Status sesi: DRAFT | OPEN | CLOSED | ANALYZED.", examples=["OPEN"]
    )
    sesi_periode: str = Field(description="Periode sesi (YYYY-MM).", examples=["2025-06"])
    sesi_jabatan_id: str = Field(description="ID jabatan yang dikaji.")
    jumlah_log: int = Field(description="Jumlah log harian yang sudah diisi.")
