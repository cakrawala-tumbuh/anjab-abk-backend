"""Skema Pydantic sesi partisipasi redesain (sheet SESI; BUKAN Time Study)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .kosakata import JenisKegiatanSesi, StatusIzinSesi


class SesiCreate(BaseModel):
    """Payload keterlibatan satu orang × satu sesi; pasangan `kode_sesi`+`kode_orang` unik."""

    model_config = ConfigDict(extra="forbid")

    kode_sesi: str = Field(
        min_length=1,
        max_length=20,
        description="Sesi_ID, dibagi semua peserta satu kegiatan (diisi Tim).",
        examples=["S-01"],
    )
    kode_orang: str = Field(
        min_length=1, max_length=20, description="Kode orang peserta.", examples=["O-0001"]
    )
    sekolah_id: str | None = Field(default=None, max_length=40, description="ID sekolah.")
    peran: str = Field(min_length=1, max_length=200, description="Peran orang pada sesi.")
    jenis_kegiatan: JenisKegiatanSesi = Field(description="Jenis kegiatan sesi.")
    menit_rencana: int | None = Field(default=None, ge=0, description="Menit yang direncanakan.")
    menit_disepakati: int | None = Field(default=None, ge=0, description="Menit yang disepakati.")
    waktu_kalender: str | None = Field(default=None, description="Keterangan waktu kalender.")
    catatan: str | None = None
    status_izin: StatusIzinSesi = Field(
        default="Belum ditetapkan", description="Informasi izin; tidak memblokir apa pun."
    )
    versi_izin: str | None = Field(default=None, max_length=50)
    pic_kode_orang: str | None = Field(default=None, max_length=20, examples=["O-0002"])
    tindak_lanjut: str | None = None
    masalah_ids: list[str] = Field(
        default_factory=list, description="ID masalah redesain yang terkait sesi ini."
    )


class SesiUpdate(BaseModel):
    """Payload ubah parsial sesi.

    Field nullable boleh dikosongkan dengan `null`; field wajib yang dikirim `null`
    diabaikan. `masalah_ids` bila dikirim mengganti seluruh tautan (ganti-penuh).
    """

    model_config = ConfigDict(extra="forbid")

    kode_sesi: str | None = Field(default=None, min_length=1, max_length=20)
    kode_orang: str | None = Field(default=None, min_length=1, max_length=20)
    sekolah_id: str | None = Field(default=None, max_length=40)
    peran: str | None = Field(default=None, min_length=1, max_length=200)
    jenis_kegiatan: JenisKegiatanSesi | None = None
    menit_rencana: int | None = Field(default=None, ge=0)
    menit_disepakati: int | None = Field(default=None, ge=0)
    waktu_kalender: str | None = None
    catatan: str | None = None
    status_izin: StatusIzinSesi | None = None
    versi_izin: str | None = Field(default=None, max_length=50)
    pic_kode_orang: str | None = Field(default=None, max_length=20)
    tindak_lanjut: str | None = None
    masalah_ids: list[str] | None = None


class SesiRead(BaseModel):
    """Satu baris keterlibatan orang × sesi."""

    id: str = Field(description="ID baris sesi (UUID v4).")
    kode_sesi: str
    kode_orang: str
    sekolah_id: str | None
    peran: str
    jenis_kegiatan: JenisKegiatanSesi
    menit_rencana: int | None
    menit_disepakati: int | None
    waktu_kalender: str | None
    catatan: str | None
    status_izin: StatusIzinSesi
    versi_izin: str | None
    pic_kode_orang: str | None
    tindak_lanjut: str | None
    masalah_ids: list[str] = Field(description="ID masalah terkait, terurut.")
    created_at: datetime
    updated_at: datetime


class RekapOrangRead(BaseModel):
    """Rekap menit keterlibatan per orang unik (read-model)."""

    kode_orang: str = Field(examples=["O-0001"])
    jumlah_sesi: int = Field(description="Jumlah `kode_sesi` berbeda yang diikuti orang ini.")
    total_menit_rencana: int | None = Field(
        description="Jumlah menit rencana; NULL diabaikan, semua NULL → null."
    )
    total_menit_disepakati: int | None = Field(
        description="Jumlah menit disepakati; NULL diabaikan, semua NULL → null."
    )
