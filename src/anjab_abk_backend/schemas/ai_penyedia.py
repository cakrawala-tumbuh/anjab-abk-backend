"""Skema status pengaturan penyedia model AI. Tidak pernah memuat kredensial utuh."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from ..ai.penyedia import AiEffort, AiPenyediaMode

__all__ = ["AiPenyediaAksi", "AiPenyediaStatusRead"]


class AiPenyediaAksi(StrEnum):
    """Aksi pada event pengaturan penyedia AI."""

    UBAH_MODE = "UBAH_MODE"
    UBAH_MODEL = "UBAH_MODEL"
    PASANG_KREDENSIAL = "PASANG_KREDENSIAL"
    HAPUS_KREDENSIAL = "HAPUS_KREDENSIAL"


class AiPenyediaStatusRead(BaseModel):
    """Status pengaturan penyedia AI yang berlaku."""

    mode: AiPenyediaMode = Field(description="Penyedia terpilih; MATI bila belum diatur.")
    model: str = Field(description="Model efektif (bawaan bila belum diubah).")
    effort: AiEffort = Field(description="Effort efektif (bawaan bila belum diubah).")
    kredensial_terpasang: bool = Field(description="True bila kunci API tersimpan.")
    kredensial_akhiran: str | None = Field(
        default=None, description="Empat karakter terakhir kunci API."
    )
    kredensial_terbaca: bool = Field(
        description="True bila kunci tersimpan dapat didekripsi dengan kunci induk saat ini."
    )
    enkripsi_siap: bool = Field(description="True bila kunci induk deployment sah.")
    diperbarui_oleh: str | None = Field(default=None, description="Aktor perubahan terakhir.")
    pada: datetime | None = Field(default=None, description="Waktu perubahan terakhir (UTC).")
