"""Skema Pydantic untuk endpoint kuesioner partisipan (WCP)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WcpKuesionerItemRead(BaseModel):
    """Responden WCP diperkaya info instrumen — dipakai endpoint /kuesioner/saya."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID responden.", examples=["wrsp_a1b2c3d4"])
    catatan: str | None = Field(default=None, description="Catatan instrumen WCP.")
    sudah_submit: bool = Field(description="True jika jawaban sudah disubmit.")
    submitted_at: datetime | None = Field(default=None, description="Waktu submit.")
    created_at: datetime = Field(description="Waktu pendaftaran.")
    instrumen_status: str = Field(
        description="Status instrumen: OPEN | CLOSED | ANALYZED.", examples=["OPEN"]
    )
