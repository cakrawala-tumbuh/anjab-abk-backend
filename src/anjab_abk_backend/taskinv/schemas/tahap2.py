"""Skema Pydantic untuk review koordinator Tahap 2 Task Inventory."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TiTahap2TaskRead(BaseModel):
    """Satu task yang perlu diputuskan koordinator di Tahap 2."""

    model_config = ConfigDict(from_attributes=True)

    task_kode: str = Field(description="Kode task.", examples=["TIf0b59714"])
    n_relevan: int = Field(description="Jumlah anggota yang memilih task ini sebagai relevan.")
    n_total: int = Field(description="Total anggota panel yang sudah submit Tahap 1.")
    disetujui: bool | None = Field(
        default=None,
        description="Keputusan koordinator: True=disetujui, False=ditolak, None=belum diputuskan.",
    )


class TiTahap2KeputusanItem(BaseModel):
    """Satu keputusan koordinator untuk satu task."""

    model_config = ConfigDict(extra="forbid")

    task_kode: str = Field(description="Kode task.", examples=["TIf0b59714"])
    disetujui: bool = Field(description="True jika koordinator menyetujui task ini masuk Tahap 3.")


class TiTahap2Submit(BaseModel):
    """Payload submit keputusan koordinator untuk seluruh task Tahap 2."""

    model_config = ConfigDict(extra="forbid")

    keputusan: list[TiTahap2KeputusanItem] = Field(
        description="Daftar keputusan koordinator per task.",
        min_length=1,
    )


class TiTahap2ReviewRead(BaseModel):
    """Status review Tahap 2 koordinator untuk satu sesi."""

    model_config = ConfigDict(from_attributes=True)

    sesi_id: str = Field(description="ID sesi.", examples=["tises_a1b2c3d4"])
    tasks: list[TiTahap2TaskRead] = Field(description="Task yang perlu diputuskan koordinator.")
    jumlah_belum_diputuskan: int = Field(
        description="Jumlah task yang belum ada keputusan koordinator."
    )
    submitted_at: datetime | None = Field(
        default=None, description="Waktu terakhir keputusan disubmit."
    )
