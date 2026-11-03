"""Skema Pydantic untuk register pengecualian sesi OPM (backlog `#69`, A9)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AlasanPengecualian = Literal[
    "TI_DETAIL_UNMATCHED",
    "OPM_STD_MISSING",
    "OPM_RATING_MISSING",
]
"""Kode alasan pengecualian TI-OPM yang dikenal register."""

StatusVerifikasi = Literal["VERIFIED", "UNVERIFIED"]
"""Status verifikasi turunan sesi: `UNVERIFIED` bila ada >= 1 pengecualian `OPEN`."""


class OpmPengecualianRead(BaseModel):
    """Satu baris register pengecualian sesi OPM."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID baris register (UUID v4).")
    sesi_id: str = Field(description="ID sesi OPM pemilik pengecualian.")
    task_kode: str = Field(description="Kode task yang bermasalah.", examples=["T-012"])
    alasan: AlasanPengecualian = Field(
        description=(
            "Kode alasan: `TI_DETAIL_UNMATCHED` (kode terpilih TI tak ada di katalog saat"
            " snapshot), `OPM_STD_MISSING` (task tanpa ketiga nilai standar),"
            " `OPM_RATING_MISSING` (task tanpa satu pun rating saat analisis)."
        )
    )
    keterangan: str | None = Field(default=None, description="Keterangan bebas, bila ada.")
    status: str = Field(description="Status pengecualian (saat ini selalu `OPEN`).")
    created_at: datetime = Field(description="Waktu pencatatan (UTC, ISO-8601).")
