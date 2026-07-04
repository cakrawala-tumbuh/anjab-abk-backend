"""Skema Pydantic untuk endpoint kuesioner partisipan (Time Study)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TsKuesionerItemRead(BaseModel):
    """Penugasan TS milik pengguna yang sedang login — dipakai endpoint /kuesioner/saya."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID penugasan.", examples=["tpn_a1b2c3d4"])
    aktif: bool = Field(description="Status aktif penugasan.")
    jumlah_log: int = Field(description="Jumlah log harian yang sudah diisi.")
    created_at: datetime = Field(description="Waktu penugasan dibuat.")
