"""Skema cerita pra-bank dan log paparan bank tugas Task Inventory (backlog #131)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JenisPaparan(StrEnum):
    """Jenis materi yang diperlihatkan kepada responden; nilai lain ditolak CHECK."""

    BANK_TUGAS = "BANK_TUGAS"
    CONTOH_TUGAS = "CONTOH_TUGAS"


class StatusPaparan(StrEnum):
    """Status cerita saat sebuah paparan terjadi (disimpan pada tiap baris log)."""

    LOCKED_PRE_EXPOSURE = "LOCKED_PRE_EXPOSURE"
    EXPOSED = "EXPOSED"


class ExposureState(StrEnum):
    """Status paparan responden, diturunkan dari paparan pertamanya."""

    BELUM_TERPAPAR = "BELUM_TERPAPAR"
    LOCKED_PRE_EXPOSURE = "LOCKED_PRE_EXPOSURE"
    EXPOSED = "EXPOSED"


class CeritaPrabankUpsert(BaseModel):
    """Payload `PUT .../cerita-prabank`: teks cerita bebas (1-20.000 karakter)."""

    model_config = ConfigDict(extra="forbid")

    teks: str = Field(
        min_length=1,
        max_length=20_000,
        description="Cerita bebas responden tentang pekerjaannya, sebelum melihat bank tugas.",
        examples=["Setiap hari saya menyiapkan perangkat ajar lalu mengajar kelas X."],
    )


class CeritaPrabankRead(BaseModel):
    """Cerita pra-bank satu responden; `frozen_at` terisi setelah dibekukan."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID cerita (UUID v4).")
    teks: str = Field(description="Teks cerita.")
    frozen_at: datetime | None = Field(
        default=None, description="Waktu server saat cerita dibekukan; null bila masih draf."
    )


class PaparanCreate(BaseModel):
    """Payload `POST .../paparan`. Waktu paparan SELALU dari server (`extra=forbid`)."""

    model_config = ConfigDict(extra="forbid")

    jenis: JenisPaparan = Field(description="Jenis materi yang diperlihatkan.")


class PaparanRead(BaseModel):
    """Satu baris log paparan (append-only)."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID paparan (UUID v4).")
    jenis: JenisPaparan = Field(description="Jenis materi yang diperlihatkan.")
    terjadi_pada: datetime = Field(description="Waktu server saat paparan dicatat.")
    status_saat_paparan: StatusPaparan = Field(
        description="LOCKED_PRE_EXPOSURE bila cerita sudah beku, selain itu EXPOSED."
    )


class PrabankRead(BaseModel):
    """Ringkasan status pra-bank satu responden."""

    cerita: CeritaPrabankRead | None = Field(description="Cerita responden; null bila belum ada.")
    frozen_at: datetime | None = Field(description="Waktu cerita dibekukan; null bila belum.")
    first_exposed_at: datetime | None = Field(
        description="Waktu paparan pertama; null bila belum pernah terpapar."
    )
    exposure_state: ExposureState = Field(description="Status paparan dari paparan pertama.")
