"""Skema usulan hasil fungsi AI non-narasi: jenis sasaran, hasil serap, dan proyeksi ringkas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["AiUsulanRingkas", "HasilSerapUsulan", "SasaranUsulan"]


class SasaranUsulan(StrEnum):
    """Jenis objek sasaran sebuah usulan AI (`ai_usulan.sasaran_jenis`)."""

    NARASI_KASUS = "NARASI_KASUS"
    NARASI_SUMBER = "NARASI_SUMBER"


class HasilSerapUsulan(StrEnum):
    """Nilai `ai_usulan.hasil_serap`."""

    USULAN_DIBUAT = "USULAN_DIBUAT"
    EVIDENCE_GAP = "EVIDENCE_GAP"
    MANUAL = "MANUAL"


class AiUsulanRingkas(BaseModel):
    """Proyeksi usulan tanpa `isi`, `amplop`, maupun `output_hash` (keluaran model)."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="UUID v4 usulan.")
    fungsi: str = Field(description="Kode fungsi AI.", examples=["P09"])
    sasaran_jenis: SasaranUsulan = Field(description="Jenis objek sasaran.")
    sasaran_id: str = Field(description="Id objek sasaran (polimorfik, tanpa FK).")
    job_id: str = Field(description="Id `async_job` hasil pengajuan.")
    ai_run_id: str = Field(description="Id `ai_run` (satu run, satu usulan).")
    sumber_ids: list[str] = Field(description="Id sumber yang diajukan.")
    diminta_oleh: str = Field(description="Subjek pemohon.")
    created_at: datetime = Field(description="Waktu pengajuan.")
    diserap_at: datetime | None = Field(default=None, description="Null sampai run diserap.")
    hasil_serap: HasilSerapUsulan | None = Field(default=None, description="Hasil serap.")
    kode_serap: list[str] | None = Field(default=None, description="Kode alasan hasil `MANUAL`.")
