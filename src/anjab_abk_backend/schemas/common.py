"""Skema lintas-resource: Health, Message, Page[T], Cabang, dan amplop error."""

from __future__ import annotations

from enum import StrEnum
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

Cabang = Literal["Bandung", "Semarang"]
"""Cabang lokasi (yayasan) — enum aplikasi, bukan FK, tanpa tabel master.

Sumber tunggal. Dipakai baik oleh entitas SESI (Task Inventory & OPM, sejak
backlog `anjab-abk-backend#37`) maupun entitas SEKOLAH (`sekolah.cabang`, sejak
backlog `anjab-abk-backend#40` — penanda cabang partisipan lewat sekolahnya).
"""

CabangSesi = Cabang
"""Alias historis untuk `Cabang`, dipertahankan agar `from .sesi import
CabangSesi` yang sudah dipakai `taskinv/schemas/sesi.py`, `taskinv/schemas/
hasil.py`, `taskinv/schemas/kuesioner.py`, dan modul `opm/schemas/*` tetap jalan
tanpa perubahan (backlog `anjab-abk-backend#40`)."""


class Health(BaseModel):
    status: str = Field(description="Status ringkas.", examples=["ok"])
    version: str = Field(description="Versi aplikasi.", examples=["0.1.0"])


class Message(BaseModel):
    message: str = Field(description="Pesan.", examples=["Berhasil."])


class Page(BaseModel, Generic[T]):
    items: list[T] = Field(description="Item pada halaman ini.")
    total: int = Field(description="Total item tersedia.", examples=[42])
    limit: int = Field(description="Maksimum item per halaman.", examples=[20])
    offset: int = Field(description="Jumlah item yang dilewati.", examples=[0])


class BulkSkipped(BaseModel):
    partisipan_id: str = Field(description="ID partisipan yang dilewati.")
    alasan: str = Field(
        description=(
            "Kode alasan dilewati: 'sudah_terdaftar' | 'duplikat_input' |"
            " 'bukan_anggota_sme_panel' | 'kapasitas_penuh' | 'beda_cabang'"
            " (backlog `anjab-abk-backend#41` — partisipan bercabang sekolah"
            " berbeda dari cabang sesi; hanya dipakai auto-populate responden"
            " sesi Task Inventory)."
        ),
        examples=["sudah_terdaftar"],
    )


class BulkAssignResult(BaseModel, Generic[T]):
    created: list[T] = Field(description="Baris yang berhasil dibuat.")
    skipped: list[BulkSkipped] = Field(description="Partisipan yang dilewati beserta alasannya.")


class ErrorDetail(BaseModel):
    loc: list[str] | None = Field(default=None, description="Lokasi field penyebab.")
    msg: str = Field(description="Penjelasan singkat.")
    type: str = Field(description="Tipe error Pydantic.")
    code: str | None = Field(
        default=None, description="Kode mesin-terbaca stabil.", examples=["not_allowed"]
    )


class ErrorResponse(BaseModel):
    error: str = Field(description="Kode error stabil.", examples=["not_found"])
    message: str = Field(description="Pesan ramah-manusia.", examples=["Data tidak ditemukan."])
    request_id: str | None = Field(default=None, description="Korelasi dengan log.")
    details: list[ErrorDetail] | None = Field(default=None, description="Rincian validasi.")


class FiturKode(StrEnum):
    """Kode lima fungsi yang dapat dimatikan secara independen (feature flag).

    Nilai literal mengikuti paket kajian; urutan anggota = urutan di respons
    `GET /api/v1/system/fitur`.
    """

    AI_NARRATIVE_DRAFT = "AI_NARRATIVE_DRAFT"
    PARTICIPANT_VALIDATION = "PARTICIPANT_VALIDATION"
    WCP_DCS_SCORING = "WCP_DCS_SCORING"
    RESEARCH_EXPORT = "RESEARCH_EXPORT"
    CHANGE_AUTHORIZATION = "CHANGE_AUTHORIZATION"


class FiturRead(BaseModel):
    kode: FiturKode = Field(description="Kode fungsi.", examples=["WCP_DCS_SCORING"])
    aktif: bool = Field(description="True bila fungsi diaktifkan lewat environment.")
    keterangan: str = Field(description="Penjelasan singkat fungsi yang digerbang flag ini.")


class FiturListRead(BaseModel):
    items: list[FiturRead] = Field(description="Selalu lima entri, urutan sesuai enum.")


class HasilRawItemRead(BaseModel):
    """Agregat deskriptif RAW satu item instrumen WCP/DCS (mode `RAW_ONLY`).

    Nilai jawaban dipakai apa adanya: tanpa reverse scoring dan tanpa rata-rata per
    dimensi/sub-skala.
    """

    item_id: str = Field(description="Kode item.", examples=["D1a"])
    kelompok_kode: str = Field(
        description="Kode dimensi (WCP) atau sub-skala (DCS) pemilik item.", examples=["DEMAND"]
    )
    urutan: int = Field(description="Urutan global item.", examples=[1])
    n: int = Field(description="Jumlah responden yang menjawab item ini.", examples=[7])
    n_kosong: int = Field(
        description="Jumlah responden ber-submit yang tidak menjawab item ini.", examples=[0]
    )
    frekuensi: dict[str, int] = Field(
        description='Frekuensi jawaban raw, kunci "1".."5".',
        examples=[{"1": 0, "2": 1, "3": 2, "4": 3, "5": 1}],
    )
    mean_raw: float | None = Field(
        default=None, description="Rata-rata raw; null bila n < 1.", examples=[3.57]
    )
    sd_raw: float | None = Field(
        default=None, description="Simpangan baku sampel raw; null bila n < 2.", examples=[0.98]
    )
