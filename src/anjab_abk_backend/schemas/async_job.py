"""Skema job asinkron: enum status, aturan transisi, dan proyeksi baca."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .common import FiturKode

__all__ = ["TRANSISI_SAH", "AsyncJobRead", "StatusJob"]


class StatusJob(StrEnum):
    """Status siklus hidup job asinkron.

    Untuk fitur `AI_*`, `PENDING` adalah padanan `AI_PENDING` pada paket kajian.
    """

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


TRANSISI_SAH: dict[StatusJob, frozenset[StatusJob]] = {
    StatusJob.PENDING: frozenset({StatusJob.RUNNING}),
    StatusJob.RUNNING: frozenset({StatusJob.SUCCEEDED, StatusJob.FAILED, StatusJob.MANUAL_REVIEW}),
    StatusJob.FAILED: frozenset({StatusJob.PENDING}),
    StatusJob.SUCCEEDED: frozenset(),
    StatusJob.MANUAL_REVIEW: frozenset(),
}
"""Transisi sah per status asal; `SUCCEEDED` dan `MANUAL_REVIEW` terminal."""


class AsyncJobRead(BaseModel):
    """Status sebuah job asinkron (tanpa `dibuat_oleh`)."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="UUID v4 job.")
    fitur: FiturKode = Field(description="Fungsi (feature flag) pemilik job.")
    jenis: str = Field(description="Jenis job di dalam fitur.", examples=["draf_narasi"])
    status: StatusJob = Field(description="Status job saat ini.")
    ref_id: str | None = Field(default=None, description="Id objek sasaran job.")
    error_code: str | None = Field(default=None, description="Kode galat bila gagal.")
    percobaan: int = Field(description="Jumlah retry (FAILED -> PENDING).")
    created_at: datetime = Field(description="Waktu job dibuat (UTC).")
    updated_at: datetime = Field(description="Waktu perubahan terakhir (UTC).")
