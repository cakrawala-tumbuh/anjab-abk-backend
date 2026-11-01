"""Skema Pydantic alternatif redesain (sheet ALTERNATIF; BUKAN bagian skor K1-K4)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .kosakata import OpsiAlternatif, StatusTelaahAlternatif, YaTidak


class AlternatifCreate(BaseModel):
    """Payload alternatif baru; `kode` dibangkitkan sistem (`U-001`, global)."""

    model_config = ConfigDict(extra="forbid")

    masalah_id: str = Field(description="ID masalah redesain yang dicarikan alternatif.")
    opsi: OpsiAlternatif = Field(description="Jenis alternatif.")
    alur_kini_vs_usulan: str = Field(min_length=1, description="Alur kini dibanding alur usulan.")
    pihak_asal_jabatan_id: str | None = Field(
        default=None, max_length=40, description="ID jabatan pihak asal (bukan orang)."
    )
    pihak_penerima_jabatan_id: str | None = Field(
        default=None, max_length=40, description="ID jabatan penerima; wajib bila opsi pengalihan."
    )
    komitmen_penerima: str | None = None
    jadwal_puncak: str | None = None
    keterampilan_akses: str | None = None
    tambahan_bersih: str | None = None
    risiko_layanan: str | None = None
    gap_penerima: YaTidak = Field(default="Belum tahu", description="Ada gap pada penerima?")
    status_telaah: StatusTelaahAlternatif = Field(default="Belum ditelaah")
    pemutus_kode_orang: str | None = Field(default=None, max_length=20, examples=["O-0001"])
    keputusan: str | None = None
    prasyarat_monitoring: str | None = None
    catatan_versi_bukti: str | None = None


class AlternatifUpdate(BaseModel):
    """Payload ubah parsial alternatif. `kode` dan `masalah_id` tidak dapat diubah.

    Field nullable boleh dikosongkan dengan `null`; field wajib yang dikirim `null` diabaikan.
    """

    model_config = ConfigDict(extra="forbid")

    opsi: OpsiAlternatif | None = None
    alur_kini_vs_usulan: str | None = Field(default=None, min_length=1)
    pihak_asal_jabatan_id: str | None = Field(default=None, max_length=40)
    pihak_penerima_jabatan_id: str | None = Field(default=None, max_length=40)
    komitmen_penerima: str | None = None
    jadwal_puncak: str | None = None
    keterampilan_akses: str | None = None
    tambahan_bersih: str | None = None
    risiko_layanan: str | None = None
    gap_penerima: YaTidak | None = None
    status_telaah: StatusTelaahAlternatif | None = None
    pemutus_kode_orang: str | None = Field(default=None, max_length=20)
    keputusan: str | None = None
    prasyarat_monitoring: str | None = None
    catatan_versi_bukti: str | None = None


class AlternatifRead(BaseModel):
    """Satu alternatif redesain."""

    id: str = Field(description="ID alternatif (UUID v4).")
    kode: str = Field(description="Kode alternatif.", examples=["U-001"])
    masalah_id: str
    opsi: OpsiAlternatif
    alur_kini_vs_usulan: str
    pihak_asal_jabatan_id: str | None
    pihak_penerima_jabatan_id: str | None
    komitmen_penerima: str | None
    jadwal_puncak: str | None
    keterampilan_akses: str | None
    tambahan_bersih: str | None
    risiko_layanan: str | None
    gap_penerima: YaTidak
    status_telaah: StatusTelaahAlternatif
    pemutus_kode_orang: str | None
    keputusan: str | None
    prasyarat_monitoring: str | None
    catatan_versi_bukti: str | None
    created_at: datetime
    updated_at: datetime
