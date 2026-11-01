"""Skema Pydantic konfirmasi sekolah (sheet KONFIRMASI / Lembar Konfirmasi).

Sekolah mengisi sendiri tanpa fasilitator, sehingga urutan anti-persetujuan-semu
ditegakkan sistem: cerita bebas (`cerita_sebelum`) dikunci lebih dulu, baru rumusan
dugaan Tim ditampilkan, baru penilaian bagian C–E diisi. Rumusan hipotesis TIDAK
pernah ikut di skema baca konfirmasi maupun daftar masalah sekolah — hanya dibuka
lewat aksi `tampilkan-dugaan` (`DugaanRead`).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .kosakata import Indikasi, Kesesuaian, Skala, StatusAwal, StatusKonfirmasi, SumberKonfirmasi

FIELD_BAGIAN_C_E = (
    "kesesuaian",
    "koreksi",
    "masalah_baru",
    "alasan_k",
    "bukti_dapat_diperiksa",
    "hal_belum_jelas",
    "catatan_independensi",
    "catatan_akses",
    "k1",
    "k2",
    "k3",
    "k4",
    "indikasi_risiko",
)
"""Field penilaian (bagian C–E) yang baru boleh diisi setelah dugaan ditampilkan."""

FIELD_WAJIB_KIRIM = ("peran", "kesesuaian", "k1", "k2", "k3", "k4", "indikasi_risiko")
"""Field yang wajib terisi saat `kirim` (`Belum tahu` sah, kosong tidak)."""


class MasalahSekolahRead(BaseModel):
    """Bagian A Lembar Konfirmasi: masalah yang dibuka untuk sekolah pemanggil.

    Sengaja TANPA `rumusan_hipotesis` — dugaan Tim baru boleh terlihat setelah cerita
    pengisi dikunci.
    """

    id: str = Field(description="ID masalah (UUID v4).")
    kode: str = Field(examples=["M-K01-01"])
    konteks_kode: str = Field(examples=["K-01"])
    konteks_tema: str
    periode_acuan: str
    sumber_awal_keterbatasan: str
    status_awal: StatusAwal


class KonfirmasiCreate(BaseModel):
    """Payload memulai draf konfirmasi untuk satu masalah."""

    model_config = ConfigDict(extra="forbid")

    masalah_id: str = Field(description="ID masalah yang dibuka untuk sekolah pemanggil.")


class KonfirmasiUpdate(BaseModel):
    """Payload ubah parsial draf. Field yang tidak dikirim tidak berubah.

    `cerita_sebelum` hanya selama cerita belum dikunci; field bagian C–E
    (`FIELD_BAGIAN_C_E`) hanya setelah dugaan ditampilkan.
    """

    model_config = ConfigDict(extra="forbid")

    peran: str | None = Field(
        default=None, max_length=200, description="Peran/jabatan pengisi, bukan nama."
    )
    tanggal: date | None = Field(default=None, description="Tanggal pengisian.")
    cerita_sebelum: str | None = Field(
        default=None, description="Cerita bebas pengisi SEBELUM melihat dugaan Tim."
    )
    kesesuaian: Kesesuaian | None = None
    koreksi: str | None = None
    masalah_baru: str | None = None
    alasan_k: str | None = None
    bukti_dapat_diperiksa: str | None = None
    hal_belum_jelas: str | None = None
    catatan_independensi: str | None = None
    catatan_akses: str | None = None
    k1: Skala | None = None
    k2: Skala | None = None
    k3: Skala | None = None
    k4: Skala | None = None
    indikasi_risiko: Indikasi | None = Field(
        default=None, description="Indikasi risiko (istilah Lembar Konfirmasi bagian E)."
    )


class KonfirmasiRead(BaseModel):
    """Representasi konfirmasi; tidak memuat rumusan hipotesis masalah."""

    id: str = Field(description="ID konfirmasi (UUID v4).")
    masalah_id: str
    kode_orang: str = Field(description="Pseudonim pengisi.", examples=["O-0001"])
    sekolah_id: str
    sumber: SumberKonfirmasi
    peran: str | None
    tanggal: date
    cerita_sebelum: str | None
    cerita_dikunci_pada: datetime | None
    dugaan_ditampilkan_pada: datetime | None
    dugaan_diperlihatkan: Literal["Ya", "Belum"] = Field(
        description="`Ya` bila dugaan Tim sudah ditampilkan ke pengisi, selain itu `Belum`."
    )
    dikirim_pada: datetime | None
    kesesuaian: Kesesuaian | None
    koreksi: str | None
    masalah_baru: str | None
    alasan_k: str | None
    bukti_dapat_diperiksa: str | None
    hal_belum_jelas: str | None
    catatan_independensi: str | None
    catatan_akses: str | None
    k1: Skala | None
    k2: Skala | None
    k3: Skala | None
    k4: Skala | None
    indikasi_risiko: Indikasi | None
    status: StatusKonfirmasi
    menggantikan_id: str | None
    created_at: datetime
    updated_at: datetime


class DugaanRead(BaseModel):
    """Respons `tampilkan-dugaan`: rumusan hipotesis Tim + waktu pertama kali ditampilkan."""

    rumusan_hipotesis: str
    dugaan_ditampilkan_pada: datetime


class KonfirmasiDaftarRead(KonfirmasiRead):
    """Konfirmasi pada daftar (`/saya`, daftar & search Tim): menambah penanda ralat."""

    digantikan: bool = Field(
        description="True bila ada versi ralat yang menunjuk record ini (`menggantikan_id`)."
    )


class AngkatMasalahCreate(BaseModel):
    """Payload mengangkat `masalah_baru` sebuah konfirmasi menjadi masalah register."""

    model_config = ConfigDict(extra="forbid")

    konteks_id: str = Field(description="ID konteks redesain tempat masalah baru dikelompokkan.")
    rumusan_hipotesis: str = Field(
        min_length=1, description="Rumusan hipotesis yang disusun Tim dari keterangan sekolah."
    )


class KonfirmasiLuringCreate(BaseModel):
    """Payload Tim memasukkan isian kertas atas nama pemberi keterangan (sumber `luring`).

    Field wajib sama dengan aksi `kirim` (`FIELD_WAJIB_KIRIM`); konfirmasi langsung
    berstatus `terkirim` tanpa melewati urutan cerita-dugaan.
    """

    model_config = ConfigDict(extra="forbid")

    masalah_id: str
    kode_orang: str = Field(max_length=20, description="Kode pseudonim pemberi keterangan.")
    sekolah_id: str
    peran: str = Field(min_length=1, max_length=200)
    tanggal: date | None = Field(default=None, description="Tanggal isian; default hari ini.")
    cerita_sebelum: str | None = None
    kesesuaian: Kesesuaian
    koreksi: str | None = None
    masalah_baru: str | None = None
    alasan_k: str | None = None
    bukti_dapat_diperiksa: str | None = None
    hal_belum_jelas: str | None = None
    catatan_independensi: str | None = None
    catatan_akses: str | None = None
    k1: Skala
    k2: Skala
    k3: Skala
    k4: Skala
    indikasi_risiko: Indikasi
