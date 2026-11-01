"""Skema Pydantic proses & langkah redesain (sheet ALUR: Process_ID & Step_ID).

Satu proses selalu terikat SATU masalah dan SATU sekolah (`ALUR!A3`). Langkah tidak
pernah dihapus; langkah yang tak berlaku diberi `status_langkah="Tidak berlaku"`.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .kosakata import StatusLangkah


class ProsesCreate(BaseModel):
    """Payload proses baru; `kode` dibangkitkan sistem (`P-001`, global)."""

    model_config = ConfigDict(extra="forbid")

    masalah_id: str = Field(description="ID masalah redesain (`redesain_masalah.id`).")
    sekolah_id: str = Field(
        description="ID sekolah; wajib sama dengan `masalah.sekolah_id` bila masalah bersekolah."
    )
    periode: str = Field(min_length=1, max_length=100, examples=["TA 2026/27"])
    nama_proses: str = Field(min_length=1, max_length=200, examples=["Penyusunan jadwal pelajaran"])


class ProsesUpdate(BaseModel):
    """Payload ubah parsial proses. `kode` read-only; field yang dikirim `null` diabaikan."""

    model_config = ConfigDict(extra="forbid")

    masalah_id: str | None = None
    sekolah_id: str | None = None
    periode: str | None = Field(default=None, min_length=1, max_length=100)
    nama_proses: str | None = Field(default=None, min_length=1, max_length=200)


class LangkahCreate(BaseModel):
    """Payload langkah baru pada sebuah proses; `kode` dibangkitkan (`<kode proses>-S01`)."""

    model_config = ConfigDict(extra="forbid")

    urutan: int | None = Field(
        default=None,
        ge=1,
        description="Urutan tampil; `null` = urutan terbesar proses itu + 1.",
    )
    tahap: str = Field(min_length=1, max_length=200, examples=["Pengumpulan data guru"])
    pemicu_input: str = Field(min_length=1, description="Pemicu / masukan langkah.")
    pelaksana: str = Field(
        min_length=1,
        max_length=200,
        description="Jabatan/peran pelaksana — BUKAN nama orang.",
        examples=["Wakil Kepala Sekolah Kurikulum"],
    )
    pekerjaan_sistem: str = Field(min_length=1, description="Pekerjaan / sistem yang dipakai.")
    keluaran_penerima: str = Field(min_length=1, description="Keluaran & penerimanya.")
    pemeriksa_pemutus: str | None = Field(
        default=None,
        max_length=200,
        description="Jabatan/peran pemeriksa atau pemutus — BUKAN nama orang.",
    )
    hambatan: str | None = Field(default=None, description="Hambatan yang teramati.")
    status_langkah: StatusLangkah = Field(description="Status langkah (kosakata baku).")


class LangkahUpdate(BaseModel):
    """Payload ubah parsial langkah.

    `kode` dan `proses_id` read-only. Field nullable (`pemeriksa_pemutus`, `hambatan`)
    boleh dikosongkan dengan `null`; field wajib yang dikirim `null` diabaikan.
    """

    model_config = ConfigDict(extra="forbid")

    urutan: int | None = Field(default=None, ge=1)
    tahap: str | None = Field(default=None, min_length=1, max_length=200)
    pemicu_input: str | None = Field(default=None, min_length=1)
    pelaksana: str | None = Field(default=None, min_length=1, max_length=200)
    pekerjaan_sistem: str | None = Field(default=None, min_length=1)
    keluaran_penerima: str | None = Field(default=None, min_length=1)
    pemeriksa_pemutus: str | None = Field(default=None, max_length=200)
    hambatan: str | None = None
    status_langkah: StatusLangkah | None = None


class LangkahRead(BaseModel):
    """Satu langkah proses redesain."""

    id: str = Field(description="ID langkah (UUID v4).")
    proses_id: str
    kode: str = Field(description="Kode langkah (dibangkitkan).", examples=["P-001-S01"])
    urutan: int
    tahap: str
    pemicu_input: str
    pelaksana: str
    pekerjaan_sistem: str
    keluaran_penerima: str
    pemeriksa_pemutus: str | None
    hambatan: str | None
    status_langkah: StatusLangkah
    created_at: datetime
    updated_at: datetime


class ProsesRead(BaseModel):
    """Satu proses redesain beserta langkahnya terurut `urutan`."""

    id: str = Field(description="ID proses (UUID v4).")
    kode: str = Field(description="Kode proses (dibangkitkan, global).", examples=["P-001"])
    masalah_id: str
    sekolah_id: str
    periode: str
    nama_proses: str
    langkah: list[LangkahRead] = Field(description="Langkah proses, terurut `urutan` lalu `kode`.")
    created_at: datetime
    updated_at: datetime
