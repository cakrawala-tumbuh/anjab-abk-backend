"""Skema Pydantic protokol riset (`riset_protokol`): berversi dan dapat dikunci permanen.

Protokol yang `TERKUNCI` menjadi dasar statistik, kasus negatif, dan sintesis P08. Tidak ada
skema sunting: perbaikan draf maupun revisi dibuat sebagai protokol `DRAF` baru dengan `kode`
yang sama, sehingga `versi` naik.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

POLA_KODE_PROTOKOL = r"^[A-Za-z0-9_.:-]+$"
"""Pola `kode` protokol: huruf, angka, `_`, `.`, `:`, `-`; tanpa spasi."""

BATAS_ISI = 100_000
"""Batas karakter `isi` satu protokol riset."""


class StatusProtokol(StrEnum):
    """Status protokol riset; nilai lain ditolak CHECK `ck_riset_protokol_status`."""

    DRAF = "DRAF"
    TERKUNCI = "TERKUNCI"


class RisetProtokolCreate(BaseModel):
    """Payload protokol baru. `versi`, `status`, dan pembuat ditentukan sistem."""

    model_config = ConfigDict(extra="forbid")

    kode: str = Field(
        min_length=1,
        max_length=40,
        pattern=POLA_KODE_PROTOKOL,
        description="Kode protokol (tanpa spasi); versi dihitung per kode.",
        examples=["P08-SINTESIS"],
    )
    judul: str = Field(min_length=1, max_length=200, examples=["Protokol sintesis bukti F5"])
    isi: str = Field(min_length=1, max_length=BATAS_ISI, description="Isi protokol (teks lengkap).")


class RisetProtokolRingkas(BaseModel):
    """Ringkasan protokol untuk daftar; TIDAK memuat `isi`."""

    id: str = Field(description="ID protokol (UUID v4).")
    kode: str
    versi: int = Field(description="Versi per `kode`, mulai 1.")
    judul: str
    status: StatusProtokol
    isi_hash: str | None = Field(
        description="SHA-256 heksadesimal atas UTF-8 `isi`; terisi saat dikunci."
    )
    dibuat_oleh: str = Field(description="Subjek token pembuat.")
    dikunci_oleh: str | None = Field(description="Subjek token pengunci.")
    dikunci_pada: datetime | None
    created_at: datetime
    updated_at: datetime


class RisetProtokolRead(RisetProtokolRingkas):
    """Satu protokol riset lengkap, termasuk `isi`."""

    isi: str
