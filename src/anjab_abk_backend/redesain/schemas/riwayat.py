"""Skema Pydantic riwayat perubahan redesain (append-only, hanya dibaca lewat API)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RiwayatRead(BaseModel):
    """Satu catatan riwayat perubahan entitas redesain."""

    id: str = Field(description="ID catatan riwayat (UUID v4).")
    entitas: str = Field(description="Nama entitas yang berubah.", examples=["masalah"])
    entitas_id: str = Field(description="ID entitas yang berubah.")
    aksi: str = Field(description="Jenis aksi.", examples=["create", "update", "kirim", "putuskan"])
    nilai_sebelum: dict[str, Any] | None = Field(
        default=None, description="Snapshot nilai sebelum perubahan (null untuk create)."
    )
    nilai_sesudah: dict[str, Any] | None = Field(
        default=None, description="Snapshot nilai sesudah perubahan."
    )
    pelaku_kode_orang: str | None = Field(
        default=None,
        description="Kode orang pelaku (pseudonim); null hanya untuk seed/sistem.",
    )
    waktu: datetime = Field(description="Waktu pencatatan (UTC).")
