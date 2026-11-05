"""Skema permintaan draf AI atas kasus narasi (`narasi_ai_permintaan`)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from ...schemas.async_job import StatusJob

BATAS_SUMBER_PERMINTAAN = 50
"""Jumlah maksimum `sumber_ids` pada satu permintaan."""


class PermintaanAiCreate(BaseModel):
    """Badan `POST /narasi/kasus/{id}/draf-ai`.

    `sumber_ids` boleh kosong: sumber kosong berakhir `NEED_FACT` tanpa memanggil model.
    """

    model_config = ConfigDict(extra="forbid")

    sumber_ids: list[str] = Field(
        default_factory=list,
        max_length=BATAS_SUMBER_PERMINTAAN,
        description="Id sumber narasi yang diajukan; boleh kosong.",
    )


class PermintaanAiRead(BaseModel):
    """Satu permintaan draf AI beserta status job-nya; tanpa `masukan` dan `keluaran`."""

    id: str = Field(description="UUID v4 permintaan.")
    job_id: str = Field(description="Id job asinkron.")
    job_status: StatusJob = Field(description="Status job saat dibaca.")
    job_error_code: str | None = Field(description="Kode galat job bila ada.")
    ai_run_id: str = Field(description="Id run pada register `ai_run`.")
    sumber_ids: list[str] = Field(description="Sumber yang diajukan, urut pengajuan.")
    created_at: datetime
    diserap_at: datetime | None = Field(description="Terisi saat hasil run diserap.")
    hasil_serap: str | None
    kode_serap: list[str] | None
