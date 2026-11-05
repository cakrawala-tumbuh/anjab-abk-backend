"""Skema Pydantic teks sumber narasi (`narasi_sumber`): tempelan teks tak dapat diubah."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

BATAS_TEKS = 200_000
"""Batas karakter `teks` pada satu sumber narasi."""


class JenisSumberNarasi(StrEnum):
    """Jenis sumber yang sah pada tahap T0 dan T1 (K-3); nilai lain ditolak 422."""

    SINTETIS = "SINTETIS"
    DOKUMEN_RESMI = "DOKUMEN_RESMI"


class NarasiSumberCreate(BaseModel):
    """Payload sumber narasi baru. `id` (= Source_ID) dan `teks_hash` dibangkitkan sistem."""

    model_config = ConfigDict(extra="forbid")

    judul: str = Field(min_length=1, max_length=200, examples=["Pedoman akademik 2026"])
    jenis: JenisSumberNarasi = Field(description="Jenis sumber (SINTETIS atau DOKUMEN_RESMI).")
    versi: str = Field(min_length=1, max_length=50, examples=["v1.0"])
    periode: str = Field(min_length=1, max_length=20, examples=["2026/27"])
    teks: str = Field(min_length=1, max_length=BATAS_TEKS, description="Teks sumber (tempelan).")
    izin_ai: bool = Field(
        default=False, description="Catatan izin pemakaian AI; tidak menyalakan AI."
    )
    izin_catatan: str | None = Field(default=None, description="Dasar izin; wajib bila izin_ai.")
    menggantikan_id: str | None = Field(
        default=None, max_length=36, description="ID sumber yang digantikan baris ini."
    )

    @model_validator(mode="after")
    def _izin_butuh_catatan(self) -> NarasiSumberCreate:
        """Tolak `izin_ai=true` tanpa `izin_catatan` berisi."""
        if self.izin_ai and not (self.izin_catatan and self.izin_catatan.strip()):
            raise ValueError("izin_catatan wajib diisi bila izin_ai=true.")
        return self


class NarasiSumberRingkas(BaseModel):
    """Ringkasan sumber untuk daftar/pencarian; TIDAK memuat `teks`."""

    id: str = Field(description="Source_ID (UUID v4).")
    judul: str
    jenis: JenisSumberNarasi
    versi: str
    periode: str
    teks_hash: str = Field(description="SHA-256 hex atas UTF-8 teks.")
    izin_ai: bool
    izin_catatan: str | None
    menggantikan_id: str | None
    dibuat_oleh: str
    created_at: datetime


class NarasiSumberRead(NarasiSumberRingkas):
    """Satu sumber narasi lengkap, termasuk `teks`."""

    teks: str
