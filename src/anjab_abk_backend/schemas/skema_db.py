"""Skema respons pembanding revisi skema basis data (``GET /api/v1/system/skema``)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SkemaDbRead(BaseModel):
    """Perbandingan skema basis data aktif dengan kode dan model ORM.

    Hanya memuat nama revisi, tabel, kolom, dan objek skema; tidak pernah memuat data baris.
    """

    revisi_db: list[str] = Field(
        description="Isi tabel alembic_version pada basis data aktif; kosong bila tabel tak ada.",
        examples=[["c1eacaf37063"]],
    )
    head_kode: list[str] = Field(
        description="Revisi head yang terdefinisi di migrations/versions/ pada kode ini.",
        examples=[["c1eacaf37063"]],
    )
    selaras: bool = Field(
        description="True bila revisi_db dan head_kode berisi himpunan yang sama dan tidak kosong.",
        examples=[True],
    )
    selisih_model: list[str] = Field(
        description="Selisih skema aktual terhadap model ORM, bentuk '<operasi>:<nama objek>'.",
        examples=[["remove_table:tabel_liar"]],
    )
    selisih_terbaca: bool = Field(
        description="False bila pembandingan dengan model gagal; selisih_model tak andal.",
        examples=[True],
    )
