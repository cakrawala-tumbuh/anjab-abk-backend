"""Skema Pydantic masalah redesain (sheet MASALAH): hipotesis lokal per sekolah/periode."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .kosakata import Gelombang, StatusAwal


class MasalahCreate(BaseModel):
    """Payload masalah baru; `kode` dibangkitkan sistem dari kode konteks."""

    model_config = ConfigDict(extra="forbid")

    konteks_id: str = Field(description="ID konteks redesain (`redesain_konteks.id`).")
    sekolah_id: str | None = Field(
        default=None, description='ID sekolah; `null` = "Belum ditetapkan".'
    )
    keterangan_sekolah: str | None = Field(
        default=None,
        max_length=200,
        description="Teks bebas sekolah/jenjang/cabang bila sekolah belum ditetapkan.",
        examples=["Sumber contoh TK Semarang"],
    )
    periode_acuan: str = Field(
        min_length=1, max_length=100, examples=["TA 2026/27 belum dipastikan"]
    )
    periode_pasti: bool = Field(default=False, description="True bila periode sudah pasti.")
    rumusan_hipotesis: str = Field(min_length=1, description="Rumusan hipotesis, bukan kesimpulan.")
    sumber_awal_keterbatasan: str = Field(min_length=1, description="Sumber awal & keterbatasan.")
    status_awal: StatusAwal = Field(default="Hipotesis", description="Status awal masalah.")
    gelombang: Gelombang = Field(description="Gelombang validasi usulan.")
    penjelasan_alternatif: str | None = Field(
        default=None, description="Pemeriksaan / penjelasan alternatif."
    )
    pic_kode_orang: str | None = Field(
        default=None, max_length=20, description="Kode orang penanggung jawab (pseudonim)."
    )
    uraian_tugas_ids: list[str] = Field(
        default_factory=list, description="ID uraian tugas katalog yang ditautkan."
    )


class MasalahUpdate(BaseModel):
    """Payload ubah parsial masalah.

    `kode` dan `status_awal_dibekukan_pada` read-only. `uraian_tugas_ids` bila dikirim
    MENGGANTI PENUH tautan. Field nullable boleh dikosongkan dengan `null`; field wajib
    yang dikirim `null` diabaikan.
    """

    model_config = ConfigDict(extra="forbid")

    konteks_id: str | None = None
    sekolah_id: str | None = None
    keterangan_sekolah: str | None = Field(default=None, max_length=200)
    periode_acuan: str | None = Field(default=None, min_length=1, max_length=100)
    periode_pasti: bool | None = None
    rumusan_hipotesis: str | None = Field(default=None, min_length=1)
    sumber_awal_keterbatasan: str | None = Field(default=None, min_length=1)
    status_awal: StatusAwal | None = None
    gelombang: Gelombang | None = None
    penjelasan_alternatif: str | None = None
    pic_kode_orang: str | None = Field(default=None, max_length=20)
    uraian_tugas_ids: list[str] | None = None


class MasalahStatusKonfirmasi(BaseModel):
    """Payload aksi buka/tutup masalah untuk konfirmasi sekolah."""

    model_config = ConfigDict(extra="forbid")

    dibuka: bool = Field(description="True = dibuka untuk konfirmasi sekolah; False = ditutup.")


class MasalahRead(BaseModel):
    """Satu masalah redesain beserta tautan uraian tugasnya."""

    id: str = Field(description="ID masalah (UUID v4).")
    kode: str = Field(description="Kode masalah (dibangkitkan sistem).", examples=["M-K01-01"])
    konteks_id: str
    sekolah_id: str | None
    keterangan_sekolah: str | None
    periode_acuan: str
    periode_pasti: bool
    rumusan_hipotesis: str
    sumber_awal_keterbatasan: str
    status_awal: StatusAwal
    gelombang: Gelombang
    penjelasan_alternatif: str | None
    pic_kode_orang: str | None
    dibuka_untuk_konfirmasi: bool
    status_awal_dibekukan_pada: datetime | None = Field(
        description="Saat status awal membeku (keterangan sekolah pertama); null = belum."
    )
    eskalasi_pada: datetime | None = Field(
        default=None,
        description="Saat konfirmasi ber-indikasi risiko pertama terkirim; null = belum.",
    )
    sumber_konfirmasi_id: str | None = Field(
        default=None,
        description="ID konfirmasi asal bila masalah diangkat dari `masalah_baru`; null = bukan.",
    )
    uraian_tugas_ids: list[str] = Field(description="ID uraian tugas tertaut, terurut.")
    created_at: datetime
    updated_at: datetime
