"""Skema Pydantic untuk resource `TiSesi` (sesi Task Inventory)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StatusSesi = Literal["DRAFT", "TAHAP1", "TAHAP2", "TAHAP3", "CLOSED", "ANALYZED"]
CabangSesi = Literal["Bandung", "Semarang"]


class TiSesiCreate(BaseModel):
    """Payload pembuatan sesi Task Inventory."""

    model_config = ConfigDict(extra="forbid")

    jabatan_id: str = Field(
        min_length=1,
        description="ID jabatan yang dikaji (FK ke Jabatan).",
        examples=["jbt_a1b2c3d4"],
    )
    cabang: CabangSesi = Field(description="Cabang lokasi kajian.", examples=["Bandung"])
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

    cabang: CabangSesi | None = Field(
        default=None, description="Cabang lokasi kajian.", examples=["Bandung"]
    )
    koordinator_id: str | None = Field(default=None, description="ID koordinator SME panel.")
    catatan: str | None = Field(default=None, max_length=500)


class TiSesiRead(BaseModel):
    """Representasi sesi Task Inventory yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID sesi.", examples=["tises_a1b2c3d4"])
    jabatan_id: str = Field(description="ID jabatan yang dikaji.", examples=["jbt_a1b2c3d4"])
    jabatan_nama: str | None = Field(default=None, description="Nama jabatan yang dikaji.")
    cabang: CabangSesi | None = Field(
        default=None,
        description="Cabang lokasi kajian (bisa null untuk sesi lama sebelum field ini ada).",
        examples=["Bandung"],
    )
    status: StatusSesi = Field(description="Status sesi.", examples=["DRAFT"])
    koordinator_id: str | None = Field(
        default=None, description="ID koordinator SME panel yang bertanggung jawab Tahap 2."
    )
    jumlah_task_terpilih: int | None = Field(
        default=None,
        description="Jumlah task relevan yang dibekukan saat masuk TAHAP3 (None bila belum).",
    )
    catatan: str | None = Field(default=None, description="Catatan.")
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
