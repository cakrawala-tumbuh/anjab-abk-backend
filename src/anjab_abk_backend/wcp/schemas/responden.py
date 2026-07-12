"""Skema Pydantic untuk resource `WcpResponden`."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WcpRespondenCreate(BaseModel):
    """Payload penugasan (assign) responden WCP — bulk, minimal 1 partisipan."""

    model_config = ConfigDict(extra="forbid")

    partisipan_ids: list[str] = Field(
        min_length=1,
        description="Daftar ID partisipan yang ditugaskan sebagai responden WCP (bulk).",
        examples=[["par_a1b2c3d4", "par_b2c3d4e5"]],
    )


class WcpRespondenRead(BaseModel):
    """Representasi responden yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID responden.", examples=["wrsp_a1b2c3d4"])
    nama: str | None = Field(default=None, description="Nama responden.")
    jabatan_label: str = Field(description="Label jabatan responden.")
    partisipan_id: str | None = Field(
        default=None, description="ID partisipan yang terhubung, bila ada."
    )
    sudah_submit: bool = Field(description="True jika jawaban sudah disubmit.")
    submitted_at: datetime | None = Field(default=None, description="Waktu submit jawaban.")
    created_at: datetime = Field(description="Waktu pendaftaran (UTC, ISO-8601).")
