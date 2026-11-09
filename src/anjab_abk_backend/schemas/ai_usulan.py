"""Skema usulan hasil fungsi AI non-narasi: jenis sasaran, hasil serap, dan proyeksi ringkas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "AiUsulanPutusanCreate",
    "AiUsulanPutusanRead",
    "AiUsulanPutusanRingkas",
    "AiUsulanPutusanTerakhir",
    "AiUsulanRead",
    "AiUsulanRingkas",
    "HasilSerapUsulan",
    "PutusanUsulan",
    "SasaranUsulan",
    "TingkatKoreksi",
]


class SasaranUsulan(StrEnum):
    """Jenis objek sasaran sebuah usulan AI (`ai_usulan.sasaran_jenis`).

    Dikunci CHECK `ck_ai_usulan_sasaran_jenis`. `JABATAN` dipakai P02 (sasaran `jabatan.id`);
    `REDESAIN_MASALAH` dan `PROTOKOL_RISET` disiapkan untuk fungsi berikutnya di batch yang sama
    agar tidak ada migrasi enum per fungsi.
    """

    NARASI_KASUS = "NARASI_KASUS"
    NARASI_SUMBER = "NARASI_SUMBER"
    JABATAN = "JABATAN"
    REDESAIN_MASALAH = "REDESAIN_MASALAH"
    PROTOKOL_RISET = "PROTOKOL_RISET"


class HasilSerapUsulan(StrEnum):
    """Nilai `ai_usulan.hasil_serap`."""

    USULAN_DIBUAT = "USULAN_DIBUAT"
    EVIDENCE_GAP = "EVIDENCE_GAP"
    MANUAL = "MANUAL"


class PutusanUsulan(StrEnum):
    """Putusan reviewer manusia atas usulan AI (`ai_usulan_putusan.putusan`)."""

    APPROVE = "APPROVE"
    REVISE = "REVISE"
    REJECT = "REJECT"


class TingkatKoreksi(StrEnum):
    """Tingkat koreksi reviewer (`ai_usulan_putusan.tingkat_koreksi`)."""

    MINOR = "MINOR"
    MAJOR = "MAJOR"
    CRITICAL = "CRITICAL"


_CATATAN_MIN = 5


class AiUsulanPutusanCreate(BaseModel):
    """Body putusan reviewer. Aktor tidak pernah dibaca dari body (diambil dari token).

    Kombinasi sah: `APPROVE` tanpa `tingkat_koreksi` dan `teks_koreksi`; `REVISE` wajib
    `teks_koreksi` dan `tingkat_koreksi`; `REJECT` wajib `catatan` (min. 5 karakter setelah
    spasi pinggir dibuang) dan `tingkat_koreksi`, tanpa `teks_koreksi`. Pesan galat tidak
    pernah menggemakan isi `catatan` atau `teks_koreksi`.
    """

    putusan: PutusanUsulan = Field(description="Putusan reviewer.")
    tingkat_koreksi: TingkatKoreksi | None = Field(
        default=None, description="Wajib untuk REVISE dan REJECT; dilarang untuk APPROVE."
    )
    catatan: str | None = Field(
        default=None, max_length=5000, description="Wajib (min. 5 karakter) untuk REJECT."
    )
    teks_koreksi: str | None = Field(
        default=None, max_length=20000, description="Wajib untuk REVISE; dilarang selain itu."
    )

    @model_validator(mode="after")
    def _periksa_kombinasi(self) -> AiUsulanPutusanCreate:
        """Tegakkan kombinasi putusan/field tanpa menggemakan teks bebas.

        Raises:
            ValueError: kombinasi tidak sah (menjadi 422); pesan berupa kalimat tetap.
        """
        koreksi = (self.teks_koreksi or "").strip()
        catatan = (self.catatan or "").strip()
        if self.putusan is PutusanUsulan.APPROVE:
            if self.tingkat_koreksi is not None or self.teks_koreksi is not None:
                raise ValueError("APPROVE tidak boleh membawa tingkat_koreksi atau teks_koreksi.")
            return self
        if self.tingkat_koreksi is None:
            raise ValueError("tingkat_koreksi wajib untuk REVISE dan REJECT.")
        if self.putusan is PutusanUsulan.REVISE:
            if not koreksi:
                raise ValueError("teks_koreksi wajib untuk REVISE.")
        else:
            if len(catatan) < _CATATAN_MIN:
                raise ValueError(f"catatan wajib minimal {_CATATAN_MIN} karakter untuk REJECT.")
            if self.teks_koreksi is not None:
                raise ValueError("teks_koreksi hanya untuk REVISE.")
        return self


class AiUsulanPutusanRingkas(BaseModel):
    """Putusan terbaru atas satu usulan untuk daftar dan pencarian, tanpa teks bebas.

    Sengaja tanpa `actor_key` (subjek reviewer): identitas itu hanya keluar dari detail
    usulan (`AiUsulanPutusanTerakhir`) dan respons `POST .../putusan`, bukan dari baris
    daftar. Tanpa `catatan` dan `teks_koreksi`.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="UUID v4 putusan.")
    putusan: PutusanUsulan = Field(description="Putusan reviewer.")
    tingkat_koreksi: TingkatKoreksi | None = Field(default=None, description="Tingkat koreksi.")
    created_at: datetime = Field(description="Waktu putusan.")


class AiUsulanPutusanTerakhir(AiUsulanPutusanRingkas):
    """Putusan terbaru atas satu usulan untuk detail: ringkas ditambah `actor_key`.

    Tanpa teks bebas (`catatan`, `teks_koreksi`). Dipakai `AiUsulanRead.putusan_terakhir`;
    daftar dan pencarian memakai `AiUsulanPutusanRingkas`.
    """

    actor_key: str = Field(description="Subjek reviewer (dari token).")


class AiUsulanPutusanRead(AiUsulanPutusanTerakhir):
    """Satu putusan lengkap; hanya keluar dari rute POST dan detail usulan."""

    usulan_id: str = Field(description="Id usulan yang diputus.")
    catatan: str | None = Field(default=None, description="Catatan reviewer.")
    teks_koreksi: str | None = Field(default=None, description="Teks koreksi (REVISE).")


class AiUsulanRingkas(BaseModel):
    """Proyeksi daftar, pencarian, dan hasil pengajuan: sembilan field kontrak #102.

    Tidak memuat `isi`, `amplop`, `output_hash` (keluaran model) maupun `ai_run_id`,
    `sumber_ids`, dan `diminta_oleh`; ketiga terakhir (identitas pemohon dan rujukan run)
    hanya keluar dari rute detail lewat `AiUsulanRead`. Ditambah `putusan_terakhir` (#103).
    Karena `from_attributes`, objek ORM yang memuat kolom itu tetap dapat divalidasi, dan
    kolom yang tidak dideklarasikan di sini dibuang.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="UUID v4 usulan.")
    fungsi: str = Field(description="Kode fungsi AI.", examples=["P09"])
    sasaran_jenis: SasaranUsulan = Field(description="Jenis objek sasaran.")
    sasaran_id: str = Field(description="Id objek sasaran (polimorfik, tanpa FK).")
    job_id: str = Field(description="Id `async_job` hasil pengajuan.")
    created_at: datetime = Field(description="Waktu pengajuan.")
    diserap_at: datetime | None = Field(default=None, description="Null sampai run diserap.")
    hasil_serap: HasilSerapUsulan | None = Field(default=None, description="Hasil serap.")
    kode_serap: list[str] | None = Field(default=None, description="Kode alasan hasil `MANUAL`.")
    putusan_terakhir: AiUsulanPutusanRingkas | None = Field(
        default=None,
        description="Putusan reviewer terbaru tanpa `actor_key`; null bila belum ada.",
    )


class AiUsulanRead(AiUsulanRingkas):
    """Satu usulan lengkap untuk Tim Kajian: ringkas ditambah rujukan run dan keluaran model.

    `ai_run_id`, `sumber_ids`, dan `diminta_oleh` hanya ada di sini (tidak di daftar atau
    pencarian) dan wajib terisi.
    `isi` dan `amplop` adalah keluaran model (null sampai diserap) dan hanya keluar dari
    rute detail; `masukan` run tidak pernah dibuka dan `keluaran` run tidak lewat sini.
    `konteks_server` (#125) diisi server saat pengajuan, bukan keluaran model; P07 menyimpan
    `authorization_state` di sana, fungsi lain null.

    `putusan_terakhir` WAJIB dideklarasikan ulang sebagai `AiUsulanPutusanTerakhir`: Pydantic
    menyerialkan menurut tipe deklarasi dan `model_copy(update=...)` tidak memvalidasi, jadi
    tanpa deklarasi ulang ini `actor_key` hilang diam-diam dari detail.
    """

    putusan_terakhir: AiUsulanPutusanTerakhir | None = Field(
        default=None, description="Putusan terbaru dengan `actor_key`; null bila belum ada."
    )
    ai_run_id: str = Field(description="Id `ai_run` (satu run, satu usulan).")
    sumber_ids: list[str] = Field(
        description=(
            "Id sumber masukan yang diajukan, urut pengajuan. Untuk P09 entri terakhir "
            "berbentuk `versi:<id>`: draf yang dikritik, bukan baris `narasi_sumber`."
        )
    )
    diminta_oleh: str = Field(description="Subjek pemohon.")
    isi: dict[str, Any] | None = Field(default=None, description="Isi usulan; null sampai diserap.")
    amplop: dict[str, Any] | None = Field(
        default=None, description="Amplop keluaran model; null sampai diserap."
    )
    output_hash: str | None = Field(default=None, description="SHA-256 keluaran; null bila tanpa.")
    konteks_server: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Cuplikan yang diisi server saat pengajuan, bukan oleh model. P07 memuat "
            "`authorization_state`; fungsi lain null."
        ),
    )
    putusan: list[AiUsulanPutusanRead] = Field(
        default_factory=list, description="Seluruh putusan, urut waktu naik."
    )
