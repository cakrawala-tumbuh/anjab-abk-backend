"""Skema kill switch layanan AI: aksi, body alasan, dan status terhitung."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from .common import FiturKode

__all__ = ["AiSaklarAksi", "SaklarAiAlasan", "SaklarAiRead"]


class AiSaklarAksi(StrEnum):
    """Aksi pada event saklar AI."""

    MATIKAN = "MATIKAN"
    HIDUPKAN = "HIDUPKAN"


class SaklarAiAlasan(BaseModel):
    """Body ``matikan``/``hidupkan``. Aktor tidak pernah dibaca dari body (diambil dari token)."""

    alasan: str = Field(
        min_length=5,
        max_length=2000,
        description="Alasan aksi (min. 5 karakter).",
        examples=["Insiden: keluaran AI tidak wajar"],
    )


class SaklarAiRead(BaseModel):
    """Status saklar sebuah layanan AI, dihitung dari event terakhir dan flag env."""

    layanan: FiturKode = Field(description="Layanan AI yang dikendalikan.")
    flag_aktif: bool = Field(description="Nilai flag env layanan (gerbang utama).")
    dimatikan: bool = Field(description="True bila event terakhir adalah MATIKAN.")
    boleh_jalan: bool = Field(description="True hanya bila flag aktif dan tidak dimatikan.")
    alasan: str | None = Field(default=None, description="Alasan event terakhir.")
    aktor: str | None = Field(default=None, description="Subjek pelaku event terakhir.")
    pada: datetime | None = Field(default=None, description="Waktu event terakhir (UTC).")
