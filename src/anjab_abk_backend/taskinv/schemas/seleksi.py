"""Skema Pydantic untuk seleksi relevansi Tahap 1."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TiSeleksiDraftSave(BaseModel):
    """Payload draft-save (full-replace) seleksi relevansi Tahap 1.

    Menggantikan seluruh pilihan responden saat ini; boleh kosong (belum memilih
    task apapun). Kelengkapan (≥1 task terpilih) divalidasi terpisah saat
    finalisasi (`POST .../seleksi/submit`).
    """

    model_config = ConfigDict(extra="forbid")

    task_kode: list[str] = Field(
        default_factory=list,
        description="Daftar kode task yang relevan untuk responden ini saat ini.",
        examples=[["TIf0b59714", "TIa1b2c3d4"]],
    )


class TiSeleksiRead(BaseModel):
    """Representasi seleksi Tahap 1 satu responden."""

    model_config = ConfigDict(from_attributes=True)

    responden_id: str = Field(description="ID responden.", examples=["trsp_a1b2c3d4"])
    sesi_id: str = Field(description="ID sesi.", examples=["tises_a1b2c3d4"])
    task_kode: list[str] = Field(description="Daftar kode task yang dipilih relevan.")
    submitted_at: datetime | None = Field(default=None, description="Waktu submit.")
