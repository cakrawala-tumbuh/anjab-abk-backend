"""Skema Pydantic koreksi langkah ALUR (append-only) & tampilan alur untuk sekolah.

Sekolah mengisi sendiri, sehingga ia perlu melihat peta langkah draf sekolahnya — tetapi
hanya setelah dugaan ditampilkan di konfirmasinya. Koreksi disimpan sebagai catatan
terpisah per pihak dan tidak pernah mengubah langkah.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .kosakata import StatusLangkah


class KoreksiCreate(BaseModel):
    """Payload koreksi sebuah langkah.

    `konfirmasi_id` wajib bagi `sekolah-pengisi` (konfirmasi miliknya yang dugaannya
    sudah tampil); `tim-kajian` boleh tanpa dan nilainya diabaikan.
    """

    model_config = ConfigDict(extra="forbid")

    isi: str = Field(description="Isi koreksi / keterangan pemeriksa (tidak boleh kosong).")
    konfirmasi_id: str | None = Field(default=None, description="ID konfirmasi pengisi.")

    @field_validator("isi")
    @classmethod
    def _isi_tidak_kosong(cls, v: str) -> str:
        """Tolak `isi` kosong atau hanya spasi (422)."""
        if not v.strip():
            raise ValueError("isi tidak boleh kosong.")
        return v


class KoreksiRead(BaseModel):
    """Satu koreksi langkah (baris append-only)."""

    id: str = Field(description="ID koreksi (UUID v4).")
    langkah_id: str
    konfirmasi_id: str | None = Field(description="NULL bila ditulis Tim Kajian.")
    kode_orang: str = Field(description="Kode pseudonim penulis.", examples=["O-0001"])
    isi: str
    waktu: datetime


class LangkahAlurRead(BaseModel):
    """Langkah proses sebagaimana tampil bagi sekolah (tanpa kolom audit)."""

    id: str
    kode: str = Field(examples=["P-001-S01"])
    urutan: int
    tahap: str
    pemicu_input: str
    pelaksana: str
    pekerjaan_sistem: str
    keluaran_penerima: str
    pemeriksa_pemutus: str | None
    hambatan: str | None
    status_langkah: StatusLangkah


class ProsesAlurRead(BaseModel):
    """Proses milik sekolah konfirmasi beserta langkahnya terurut `urutan`."""

    id: str
    kode: str = Field(examples=["P-001"])
    periode: str
    nama_proses: str
    langkah: list[LangkahAlurRead]


class AlurRead(BaseModel):
    """Peta alur untuk satu konfirmasi: hanya proses sekolah & masalah konfirmasi itu."""

    konfirmasi_id: str
    masalah_id: str
    sekolah_id: str
    proses: list[ProsesAlurRead]
