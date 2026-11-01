"""Skema Pydantic catatan versi metode redesain (sheet PERUBAHAN)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class VersiMetodeCreate(BaseModel):
    """Payload catatan versi baru; pasangan `versi`+`bagian` harus unik."""

    model_config = ConfigDict(extra="forbid")

    versi: str = Field(min_length=1, max_length=20, examples=["v1.4"])
    tanggal: date = Field(description="Tanggal berlaku versi.")
    bagian: str = Field(min_length=1, max_length=200, examples=["Batas keputusan"])
    apa_diperbarui: str = Field(min_length=1, description="Apa yang diperbarui.")
    alasan_risiko: str = Field(min_length=1, description="Alasan / risiko yang dikendalikan.")
    status_hasil_uji: str = Field(min_length=1, description="Status dan hasil uji.")
    pemeriksa_pemutus: str = Field(
        min_length=1,
        max_length=200,
        description="Peran/jabatan pemeriksa atau pemutus (bukan nama).",
    )


class VersiMetodeUpdate(BaseModel):
    """Payload ubah parsial; field yang dikirim `null` diabaikan (semua kolom wajib)."""

    model_config = ConfigDict(extra="forbid")

    versi: str | None = Field(default=None, min_length=1, max_length=20)
    tanggal: date | None = None
    bagian: str | None = Field(default=None, min_length=1, max_length=200)
    apa_diperbarui: str | None = Field(default=None, min_length=1)
    alasan_risiko: str | None = Field(default=None, min_length=1)
    status_hasil_uji: str | None = Field(default=None, min_length=1)
    pemeriksa_pemutus: str | None = Field(default=None, min_length=1, max_length=200)


class VersiMetodeRead(BaseModel):
    """Satu catatan versi metode."""

    id: str = Field(description="ID catatan (UUID v4).")
    versi: str
    tanggal: date
    bagian: str
    apa_diperbarui: str
    alasan_risiko: str
    status_hasil_uji: str
    pemeriksa_pemutus: str
    created_at: datetime
    updated_at: datetime
