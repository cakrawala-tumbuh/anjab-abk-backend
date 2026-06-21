"""Skema Pydantic untuk resource `TiSesi` (sesi Task Inventory)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StatusSesi = Literal["DRAFT", "TAHAP1", "TAHAP2", "TAHAP3", "CLOSED", "ANALYZED"]


class TiSesiCreate(BaseModel):
    """Payload pembuatan sesi Task Inventory."""

    model_config = ConfigDict(extra="forbid")

    unit: str = Field(
        min_length=1,
        max_length=50,
        description="Unit/jenjang yang dikaji (TK/SD/SMP/SMA).",
        examples=["TK"],
    )
    kategori_jabatan: str = Field(
        min_length=1,
        max_length=200,
        description="Kategori jabatan yang dikaji.",
        examples=["Kepala Sekolah"],
    )
    periode: str = Field(
        min_length=7,
        max_length=7,
        pattern=r"^\d{4}-\d{2}$",
        description="Periode kajian format YYYY-MM.",
        examples=["2026-06"],
    )
    min_responden: int = Field(
        default=3, ge=1, description="Jumlah minimum responden.", examples=[3]
    )
    max_responden: int = Field(
        default=10, ge=1, description="Jumlah maksimum responden.", examples=[10]
    )
    koordinator_id: str | None = Field(
        default=None,
        description="ID partisipan yang menjadi koordinator SME panel (Tahap 2).",
        examples=["p_a1b2c3d4"],
    )
    catatan: str | None = Field(
        default=None, max_length=500, description="Catatan opsional untuk sesi ini."
    )


class TiSesiUpdate(BaseModel):
    """Payload pembaruan sesi Task Inventory (hanya saat DRAFT)."""

    model_config = ConfigDict(extra="forbid")

    periode: str | None = Field(default=None, min_length=7, max_length=7, pattern=r"^\d{4}-\d{2}$")
    koordinator_id: str | None = Field(default=None, description="ID koordinator SME panel.")
    min_responden: int | None = Field(default=None, ge=1)
    max_responden: int | None = Field(default=None, ge=1)
    catatan: str | None = Field(default=None, max_length=500)


class TiSesiRead(BaseModel):
    """Representasi sesi Task Inventory yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID sesi.", examples=["tises_a1b2c3d4"])
    unit: str = Field(description="Unit/jenjang.", examples=["TK"])
    kategori_jabatan: str = Field(description="Kategori jabatan.", examples=["Kepala Sekolah"])
    periode: str = Field(description="Periode kajian (YYYY-MM).", examples=["2026-06"])
    status: StatusSesi = Field(description="Status sesi.", examples=["DRAFT"])
    min_responden: int = Field(description="Minimum responden.")
    max_responden: int = Field(description="Maksimum responden.")
    koordinator_id: str | None = Field(
        default=None, description="ID koordinator SME panel yang bertanggung jawab Tahap 2."
    )
    jumlah_task_terpilih: int | None = Field(
        default=None,
        description="Jumlah task relevan yang dibekukan saat masuk TAHAP3 (None bila belum).",
    )
    catatan: str | None = Field(default=None, description="Catatan.")
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
