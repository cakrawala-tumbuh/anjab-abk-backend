"""Skema lintas-resource: Health, Message, Page[T], CabangSesi, dan amplop error."""

from __future__ import annotations

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

CabangSesi = Literal["Bandung", "Semarang"]
"""Cabang lokasi kajian sesi (Task Inventory & OPM).

Sumber tunggal — `taskinv/schemas/sesi.py` mengimpor & me-re-export nama ini
(backlog `anjab-abk-backend#37`) agar `from .sesi import CabangSesi` yang sudah
dipakai `taskinv/schemas/hasil.py`/`kuesioner.py` tetap jalan tanpa perubahan.
"""


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
            " 'bukan_anggota_sme_panel' | 'kapasitas_penuh'."
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
