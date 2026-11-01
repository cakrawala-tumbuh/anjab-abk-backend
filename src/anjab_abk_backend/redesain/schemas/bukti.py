"""Skema Pydantic bukti redesain (sheet BUKTI): rujukan teks per klaim, tanpa unggah berkas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .kosakata import JenisBukti, StatusPemeriksaanBukti, YaTidak


class BuktiCreate(BaseModel):
    """Payload bukti baru; `kode` dibangkitkan sistem (`B-0001`, global)."""

    model_config = ConfigDict(extra="forbid")

    masalah_id: str = Field(description="ID masalah redesain yang dibuktikan.")
    langkah_id: str | None = Field(
        default=None, description="ID langkah ALUR bila bukti menunjuk satu langkah."
    )
    unit_periode: str = Field(min_length=1, max_length=200, examples=["SD A, TA 2026/27"])
    jenis: JenisBukti = Field(description="Jenis sumber bukti.")
    pembuat_kode_orang: str | None = Field(default=None, max_length=20, examples=["O-0001"])
    pembuat_peran: str | None = Field(default=None, max_length=200)
    independen: YaTidak = Field(description="Apakah bukti independen dari pernyataan awal.")
    klaim_didukung: str = Field(min_length=1, description="Klaim yang didukung bukti ini.")
    klaim_tidak_didukung: str | None = Field(default=None, description="Klaim yang tidak didukung.")
    tanggal_versi_lokasi: str = Field(
        min_length=1, description="Tanggal, versi, dan lokasi/nama dokumen (rujukan teks)."
    )
    status_pemeriksaan: StatusPemeriksaanBukti = Field(default="Belum diperiksa")
    pemeriksa_kode_orang: str | None = Field(default=None, max_length=20)
    alasan: str | None = None
    catatan_privasi_gap: str | None = None


class BuktiUpdate(BaseModel):
    """Payload ubah parsial bukti. `kode` dan `masalah_id` tidak dapat diubah.

    Field nullable boleh dikosongkan dengan `null`; field wajib yang dikirim `null` diabaikan.
    """

    model_config = ConfigDict(extra="forbid")

    langkah_id: str | None = None
    unit_periode: str | None = Field(default=None, min_length=1, max_length=200)
    jenis: JenisBukti | None = None
    pembuat_kode_orang: str | None = Field(default=None, max_length=20)
    pembuat_peran: str | None = Field(default=None, max_length=200)
    independen: YaTidak | None = None
    klaim_didukung: str | None = Field(default=None, min_length=1)
    klaim_tidak_didukung: str | None = None
    tanggal_versi_lokasi: str | None = Field(default=None, min_length=1)
    status_pemeriksaan: StatusPemeriksaanBukti | None = None
    pemeriksa_kode_orang: str | None = Field(default=None, max_length=20)
    alasan: str | None = None
    catatan_privasi_gap: str | None = None


class BuktiRead(BaseModel):
    """Satu bukti redesain."""

    id: str = Field(description="ID bukti (UUID v4).")
    kode: str = Field(description="Kode bukti.", examples=["B-0001"])
    masalah_id: str
    langkah_id: str | None
    unit_periode: str
    jenis: JenisBukti
    pembuat_kode_orang: str | None
    pembuat_peran: str | None
    independen: YaTidak
    klaim_didukung: str
    klaim_tidak_didukung: str | None
    tanggal_versi_lokasi: str
    status_pemeriksaan: StatusPemeriksaanBukti
    pemeriksa_kode_orang: str | None
    alasan: str | None
    catatan_privasi_gap: str | None
    created_at: datetime
    updated_at: datetime
