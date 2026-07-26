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


class TiUsulanReviewRead(BaseModel):
    """Satu usulan uraian tugas Tahap 1 yang perlu diputuskan koordinator di Tahap 2.

    Proyeksi ringkas dari `TiUsulanRead` (`taskinv/schemas/usulan.py`) khusus untuk
    layar review koordinator — menambah `responden_nama` (bukan sekadar id) dan
    membuang `sesi_id`/`task_kode`/`created_at` yang tidak relevan di layar ini.
    """

    model_config = ConfigDict(from_attributes=True)

    usulan_id: str = Field(description="ID usulan.", examples=["tius_a1b2c3d4"])
    responden_id: str = Field(description="ID responden pengusul.", examples=["trsp_a1b2c3d4"])
    responden_nama: str | None = Field(default=None, description="Nama responden pengusul.")
    tugas_pokok: str = Field(description="Nama tugas pokok induk usulan (ter-resolve).")
    detil_tugas: str | None = Field(
        default=None, description="Nama detil tugas induk usulan (ter-resolve, bila ada)."
    )
    uraian: str = Field(description="Teks uraian tugas yang diusulkan.")
    disetujui: bool | None = Field(
        default=None,
        description="Keputusan koordinator. NULL = belum diputuskan.",
    )


class TiUsulanKeputusanItem(BaseModel):
    """Satu keputusan koordinator untuk satu usulan Tahap 1."""

    model_config = ConfigDict(extra="forbid")

    usulan_id: str = Field(description="ID usulan.", examples=["tius_a1b2c3d4"])
    disetujui: bool = Field(
        description="True jika koordinator menyetujui usulan ini masuk Tahap 3."
    )


class TiTahap2Submit(BaseModel):
    """Payload submit keputusan koordinator untuk task & usulan Tahap 2.

    `keputusan`/`keputusan_usulan` masing-masing default list kosong — submit tetap
    ditolak (422, lihat router) bila **kedua-duanya** kosong, supaya sesi yang hanya
    punya usulan (tanpa task partial) tetap bisa disubmit.
    """

    model_config = ConfigDict(extra="forbid")

    keputusan: list[TiTahap2KeputusanItem] = Field(
        default_factory=list,
        description="Daftar keputusan koordinator per task.",
    )
    keputusan_usulan: list[TiUsulanKeputusanItem] = Field(
        default_factory=list,
        description="Daftar keputusan koordinator per usulan Tahap 1.",
    )


class TiTahap2ReviewRead(BaseModel):
    """Status review Tahap 2 koordinator untuk satu sesi."""

    model_config = ConfigDict(from_attributes=True)

    sesi_id: str = Field(description="ID sesi.", examples=["tises_a1b2c3d4"])
    tasks: list[TiTahap2TaskRead] = Field(description="Task yang perlu diputuskan koordinator.")
    usulan: list[TiUsulanReviewRead] = Field(
        default_factory=list,
        description="Usulan uraian tugas Tahap 1 yang perlu diputuskan koordinator.",
    )
    jumlah_belum_diputuskan: int = Field(
        description="Jumlah task DAN usulan yang belum ada keputusan koordinator."
    )
    submitted_at: datetime | None = Field(
        default=None, description="Waktu terakhir keputusan disubmit."
    )
