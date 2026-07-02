"""Skema Pydantic untuk resource `OpmSesi` dan snapshot task-nya."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

StatusSesi = Literal["DRAFT", "OPEN", "CLOSED", "ANALYZED"]


class OpmSesiCreate(BaseModel):
    """Payload pembuatan sesi OPM."""

    model_config = ConfigDict(extra="forbid")

    jabatan_id: str = Field(
        min_length=1,
        description="ID jabatan yang dinilai (FK ke Jabatan; wajib punya SME panel).",
        examples=["jbt_a1b2c3d4"],
    )
    ti_sesi_id: str = Field(
        min_length=1,
        description="ID sesi Task Inventory sumber snapshot task (harus sudah frozen).",
        examples=["tises_a1b2c3d4"],
    )
    periode: str = Field(
        min_length=7,
        max_length=7,
        pattern=r"^\d{4}-\d{2}$",
        description="Periode survei format YYYY-MM.",
        examples=["2026-06"],
    )
    min_responden: int = Field(
        default=3, ge=1, description="Jumlah minimum responden.", examples=[3]
    )
    max_responden: int = Field(
        default=10, ge=1, description="Jumlah maksimum responden.", examples=[10]
    )
    catatan: str | None = Field(
        default=None,
        max_length=500,
        description="Catatan opsional untuk sesi ini.",
    )


class OpmSesiUpdate(BaseModel):
    """Payload pembaruan sesi OPM (hanya saat DRAFT).

    `jabatan_id` dan `ti_sesi_id` tidak dapat diubah — ganti sumber berarti hapus
    sesi lalu buat ulang.
    """

    model_config = ConfigDict(extra="forbid")

    periode: str | None = Field(
        default=None,
        min_length=7,
        max_length=7,
        pattern=r"^\d{4}-\d{2}$",
        description="Periode baru.",
    )
    min_responden: int | None = Field(default=None, ge=1, description="Minimum responden baru.")
    max_responden: int | None = Field(default=None, ge=1, description="Maksimum responden baru.")
    catatan: str | None = Field(default=None, max_length=500, description="Catatan baru.")


class OpmSesiRead(BaseModel):
    """Representasi sesi OPM yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID sesi.", examples=["opses_a1b2c3d4"])
    jabatan_id: str = Field(description="ID jabatan yang dinilai.", examples=["jbt_a1b2c3d4"])
    jabatan_nama: str | None = Field(default=None, description="Nama jabatan yang dinilai.")
    ti_sesi_id: str = Field(description="ID sesi Task Inventory sumber snapshot.")
    periode: str = Field(description="Periode survei (YYYY-MM).", examples=["2026-06"])
    status: StatusSesi = Field(description="Status sesi.", examples=["DRAFT"])
    min_responden: int = Field(description="Minimum responden.")
    max_responden: int = Field(description="Maksimum responden.")
    jumlah_task: int = Field(description="Jumlah task hasil snapshot Task Inventory.")
    catatan: str | None = Field(default=None, description="Catatan.")
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")


class OpmSesiTaskRead(BaseModel):
    """Satu baris snapshot task dalam sesi OPM."""

    model_config = ConfigDict(from_attributes=True)

    task_kode: str = Field(description="Kode task orisinal (dari Task Inventory).")
    uraian_tugas: str = Field(description="Uraian tugas.")
    tugas_pokok: str = Field(description="Nama tugas pokok induk.")
    detil_tugas: str | None = Field(default=None, description="Nama detil tugas induk, bila ada.")
    urutan: int = Field(description="Urutan tampil task.")
