"""Skema Pydantic statistik riset (`riset_statistik`): keluaran analisis per protokol terkunci.

Statistik hanya bisa dicatat untuk protokol `TERKUNCI` dan berstatus `TERVERIFIKASI` hanya
sesudah diverifikasi subjek yang bukan pengunggahnya. Tidak ada skema sunting: koreksi dibuat
sebagai baris baru.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

BATAS_KELUARAN = 200_000
"""Batas karakter `keluaran` satu statistik riset."""


class StatusStatistik(StrEnum):
    """Status statistik riset; nilai lain ditolak CHECK `ck_riset_statistik_status`."""

    DRAF = "DRAF"
    TERVERIFIKASI = "TERVERIFIKASI"


class RisetStatistikCreate(BaseModel):
    """Payload statistik baru. Protokol, status, pembuat, dan verifikasi ditentukan sistem."""

    model_config = ConfigDict(extra="forbid")

    nama_analisis: str = Field(
        min_length=1,
        max_length=200,
        description="Nama analisis yang menghasilkan keluaran.",
        examples=["Reliabilitas Cronbach alpha DCS"],
    )
    keluaran: str = Field(
        min_length=1,
        max_length=BATAS_KELUARAN,
        description="Keluaran kode analisis apa adanya (1-200.000 karakter).",
    )
    kode_sumber_ref: str = Field(
        min_length=1,
        max_length=500,
        description="Rujukan skrip + commit penghasil keluaran; wajib tak kosong.",
        examples=["analisis/dcs_alpha.py@3f2a9c1"],
    )

    @field_validator("nama_analisis", "kode_sumber_ref")
    @classmethod
    def _tidak_hanya_spasi(cls, nilai: str) -> str:
        """Tolak nilai yang hanya berisi spasi; nilai dikembalikan apa adanya (tanpa strip).

        Raises:
            ValueError: Nilai kosong setelah spasi di tepi dibuang (422).
        """
        if not nilai.strip():
            raise ValueError("Tidak boleh kosong.")
        return nilai


class RisetStatistikRead(BaseModel):
    """Satu statistik riset lengkap, termasuk `keluaran` dan jejak verifikasi."""

    id: str = Field(description="ID statistik (UUID v4).")
    protokol_id: str = Field(description="ID protokol riset `TERKUNCI` yang menjadi dasar.")
    nama_analisis: str
    keluaran: str
    kode_sumber_ref: str
    status: StatusStatistik
    dibuat_oleh: str = Field(description="Subjek token pengunggah.")
    diverifikasi_oleh: str | None = Field(
        description="Subjek token pemverifikasi; selalu berbeda dari `dibuat_oleh`."
    )
    diverifikasi_pada: datetime | None
    created_at: datetime
