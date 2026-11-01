"""Skema Pydantic kode orang (pseudonim) redesain."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class KodeOrangCreate(BaseModel):
    """Payload pendaftaran narasumber/orang baru; `kode` dibangkitkan sistem."""

    model_config = ConfigDict(extra="forbid")

    keterangan_peran: str = Field(
        min_length=1,
        max_length=200,
        description="Peran orang dalam register (tanpa nama), mis. 'Kepala sekolah SD'.",
        examples=["Narasumber dinas pendidikan"],
    )
    partisipan_id: str | None = Field(
        default=None,
        max_length=40,
        description="ID partisipan bila orang ini punya akun; null untuk narasumber tanpa akun.",
    )


class KodeOrangUpdate(BaseModel):
    """Payload ubah kode orang; hanya `keterangan_peran` yang boleh berubah."""

    model_config = ConfigDict(extra="forbid")

    keterangan_peran: str | None = Field(
        default=None, max_length=200, description="Peran orang dalam register."
    )


class KodeOrangRead(BaseModel):
    """Satu baris peta kode orang <-> partisipan (hanya terbaca `tim-kajian`)."""

    id: str = Field(description="ID baris (UUID v4).")
    kode: str = Field(description="Kode pseudonim stabil.", examples=["O-0001"])
    partisipan_id: str | None = Field(default=None, description="ID partisipan, bila ada.")
    keterangan_peran: str | None = Field(default=None, description="Peran orang tanpa nama.")
    created_at: datetime = Field(description="Waktu kode dibuat (UTC).")


class KodeOrangSaya(BaseModel):
    """Kode milik pemanggil; sengaja tidak membuka `partisipan_id`."""

    kode: str = Field(description="Kode pseudonim pemanggil.", examples=["O-0001"])
