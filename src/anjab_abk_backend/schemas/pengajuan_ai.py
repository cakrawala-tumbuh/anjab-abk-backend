"""Badan pengajuan fungsi AI berbasis katalog Task Inventory."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..ai.fungsi_p02 import POLA_KODE_P02
from ..ai.masukan import POLA_PERIODE_AI

__all__ = ["MAKS_DOKUMEN_P02", "PengajuanP02"]

MAKS_DOKUMEN_P02 = 5
"""Jumlah maksimum `narasi_sumber` pendukung per pengajuan P02."""


class PengajuanP02(BaseModel):
    """Badan `POST /task-inventory/jabatan/{jabatan_id}/normalisasi-ai` (P02).

    Tanpa teks bebas: `unit` dan `periode` berupa kode, dokumen pendukung dirujuk lewat id.

    Attributes:
        unit: Kode unit katalog untuk mempersempit baris; `null` berarti seluruh unit jabatan.
        periode: Kode periode konteks; pola `POLA_PERIODE_AI` (garis miring sah, spasi tidak).
        sumber_dokumen_ids: Id `narasi_sumber` pendukung (maks. 5), dikirim dengan jenisnya
            sendiri; duplikat diabaikan.
    """

    model_config = ConfigDict(extra="forbid")

    unit: str | None = Field(
        default=None,
        pattern=POLA_KODE_P02,
        max_length=20,
        description="Kode unit katalog; null = seluruh unit jabatan.",
        examples=["SD"],
    )
    periode: str = Field(
        pattern=POLA_PERIODE_AI,
        max_length=100,
        description="Kode periode konteks.",
        examples=["2026/27"],
    )
    sumber_dokumen_ids: list[str] = Field(
        default_factory=list,
        max_length=MAKS_DOKUMEN_P02,
        description="Id `narasi_sumber` pendukung (maks. 5).",
    )
