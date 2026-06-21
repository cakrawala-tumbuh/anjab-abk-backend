"""Skema Pydantic untuk resource `TsLog`."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DayColor = Literal["GREEN", "YELLOW", "RED"]


class TsLogCreate(BaseModel):
    """Payload pembuatan log harian Time Study."""

    model_config = ConfigDict(extra="forbid")

    tanggal: date = Field(
        description="Tanggal pencatatan (YYYY-MM-DD).",
        examples=["2025-06-01"],
    )
    waktu_masuk: str = Field(
        pattern=r"^\d{2}:\d{2}$",
        description="Waktu masuk kerja format HH:MM.",
        examples=["07:30"],
    )
    waktu_keluar: str = Field(
        pattern=r"^\d{2}:\d{2}$",
        description="Waktu keluar kerja format HH:MM.",
        examples=["16:00"],
    )
    day_color: DayColor = Field(
        description="Kategori hari: GREEN (normal), YELLOW (sedang), RED (sibuk).",
        examples=["GREEN"],
    )
    menit_core: int = Field(ge=0, description="Menit untuk Pekerjaan Inti.")
    menit_character: int = Field(ge=0, description="Menit untuk Asesmen Karakter.")
    menit_improve: int = Field(ge=0, description="Menit untuk Pengembangan Diri.")
    menit_strategic: int = Field(ge=0, description="Menit untuk Pekerjaan Strategis.")
    menit_admin: int = Field(ge=0, description="Menit untuk Administrasi.")
    menit_recovery: int = Field(ge=0, description="Menit untuk Istirahat Terstruktur.")
    catatan: str | None = Field(
        default=None,
        max_length=500,
        description="Catatan opsional.",
    )


class TsLogUpdate(BaseModel):
    """Payload pembaruan log harian Time Study (semua field opsional)."""

    model_config = ConfigDict(extra="forbid")

    tanggal: date | None = Field(default=None, description="Tanggal pencatatan (YYYY-MM-DD).")
    waktu_masuk: str | None = Field(
        default=None,
        pattern=r"^\d{2}:\d{2}$",
        description="Waktu masuk kerja format HH:MM.",
    )
    waktu_keluar: str | None = Field(
        default=None,
        pattern=r"^\d{2}:\d{2}$",
        description="Waktu keluar kerja format HH:MM.",
    )
    day_color: DayColor | None = Field(default=None, description="Kategori hari.")
    menit_core: int | None = Field(default=None, ge=0, description="Menit untuk Pekerjaan Inti.")
    menit_character: int | None = Field(
        default=None, ge=0, description="Menit untuk Asesmen Karakter."
    )
    menit_improve: int | None = Field(
        default=None, ge=0, description="Menit untuk Pengembangan Diri."
    )
    menit_strategic: int | None = Field(
        default=None, ge=0, description="Menit untuk Pekerjaan Strategis."
    )
    menit_admin: int | None = Field(default=None, ge=0, description="Menit untuk Administrasi.")
    menit_recovery: int | None = Field(
        default=None, ge=0, description="Menit untuk Istirahat Terstruktur."
    )
    catatan: str | None = Field(default=None, max_length=500, description="Catatan opsional.")


class TsLogRead(BaseModel):
    """Representasi log harian Time Study yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID log.", examples=["tlog_a1b2c3d4"])
    responden_id: str = Field(description="ID responden induk.", examples=["trsp_a1b2c3d4"])
    tanggal: date = Field(description="Tanggal pencatatan.")
    waktu_masuk: str = Field(description="Waktu masuk kerja (HH:MM).")
    waktu_keluar: str = Field(description="Waktu keluar kerja (HH:MM).")
    day_color: DayColor = Field(description="Kategori hari.")
    menit_core: int = Field(description="Menit untuk Pekerjaan Inti.")
    menit_character: int = Field(description="Menit untuk Asesmen Karakter.")
    menit_improve: int = Field(description="Menit untuk Pengembangan Diri.")
    menit_strategic: int = Field(description="Menit untuk Pekerjaan Strategis.")
    menit_admin: int = Field(description="Menit untuk Administrasi.")
    menit_recovery: int = Field(description="Menit untuk Istirahat Terstruktur.")
    catatan: str | None = Field(default=None, description="Catatan opsional.")
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
    updated_at: datetime = Field(description="Waktu pembaruan terakhir (UTC, ISO-8601).")
