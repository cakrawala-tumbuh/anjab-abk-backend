"""Skema uji kering gerbang PII sumber narasi: hanya hitungan, tanpa teks maupun nilai PII."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

BATAS_SUMBER_UJI_KERING = 500
"""Jumlah sumber maksimum per panggilan uji kering."""


class UjiKeringRequest(BaseModel):
    """Payload uji kering."""

    model_config = ConfigDict(extra="forbid")

    sumber_ids: list[str] | None = Field(
        default=None,
        max_length=10_000,
        description="Id sumber yang diuji; null = semua sumber (maksimum 500).",
    )


class UjiKeringItem(BaseModel):
    """Hasil gerbang untuk satu sumber; tidak memuat teks maupun nilai PII."""

    sumber_id: str
    jenis: str
    lolos: bool
    alasan: str | None = Field(description="Alasan penolakan gerbang; null bila lolos.")
    temuan: dict[str, int] = Field(description="{kategori PII: jumlah kemunculan}.")


class UjiKeringRead(BaseModel):
    """Rekap uji kering. Tidak ada yang disimpan; tiap panggilan menghitung ulang."""

    total: int
    lolos: int
    ditolak: int
    per_alasan: dict[str, int] = Field(description="{alasan: jumlah sumber ditolak}.")
    per_kategori: dict[str, int] = Field(
        description="{kategori PII: jumlah sumber ditolak yang memuat kategori itu}."
    )
    items: list[UjiKeringItem]
