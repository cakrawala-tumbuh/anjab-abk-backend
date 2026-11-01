"""Skema Pydantic katalog konteks redesain (K-01...K-14)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .kosakata import Gelombang

KODE_KONTEKS_POLA = r"^K-\d{2}$"
"""Pola `kode` konteks, mis. `K-01`."""


class KonteksCreate(BaseModel):
    """Payload konteks baru."""

    model_config = ConfigDict(extra="forbid")

    kode: str = Field(
        pattern=KODE_KONTEKS_POLA, description="Kode konteks unik.", examples=["K-15"]
    )
    tema: str = Field(min_length=1, max_length=200, description="Tema konteks.")
    gelombang: Gelombang = Field(description="Gelombang validasi usulan.")
    ruang_dugaan: str = Field(min_length=1, description="Ruang dugaan / variasi.")
    sumber_draft: str = Field(min_length=1, description="Sumber draf konteks.")
    batas_pemeriksaan: str = Field(
        min_length=1, description="Apa yang perlu diperiksa / batas pemeriksaan."
    )
    aktif: bool = Field(default=True, description="False = dinonaktifkan (tidak dihapus).")


class KonteksUpdate(BaseModel):
    """Payload ubah parsial konteks; `kode` tidak dapat diubah."""

    model_config = ConfigDict(extra="forbid")

    tema: str | None = Field(default=None, min_length=1, max_length=200)
    gelombang: Gelombang | None = None
    ruang_dugaan: str | None = Field(default=None, min_length=1)
    sumber_draft: str | None = Field(default=None, min_length=1)
    batas_pemeriksaan: str | None = Field(default=None, min_length=1)
    aktif: bool | None = None


class KonteksRead(BaseModel):
    """Satu konteks katalog redesain."""

    id: str = Field(description="ID konteks (UUID v4).")
    kode: str = Field(description="Kode konteks.", examples=["K-01"])
    tema: str
    gelombang: Gelombang
    ruang_dugaan: str
    sumber_draft: str
    batas_pemeriksaan: str
    aktif: bool
    created_at: datetime
    updated_at: datetime
