"""Skema Pydantic kasus negatif riset (`riset_kasus_negatif`) per protokol terkunci.

Kasus negatif adalah kasus yang tidak mendukung hipotesis; dicatat agar sintesis P08 tidak
hanya memuat bukti yang menguntungkan. Isi ditujukan untuk deskripsi kasus tersamar (tanpa data
pribadi). Tidak ada skema sunting: kasus negatif bersifat append-only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BATAS_TEKS_KASUS = 5_000
"""Batas karakter `ringkasan` dan `alasan_negatif` satu kasus negatif."""


class RisetKasusNegatifCreate(BaseModel):
    """Payload kasus negatif baru. Protokol, pembuat, dan waktu ditentukan sistem.

    Field asing ditolak (`extra="forbid"`), kecuali `dibuat_oleh` yang dibuang diam-diam:
    pencatat selalu subjek token, sehingga nilai dari body tidak pernah tersimpan.
    """

    model_config = ConfigDict(extra="forbid")

    ringkasan: str = Field(
        min_length=1,
        max_length=BATAS_TEKS_KASUS,
        description="Deskripsi kasus tersamar, tanpa data pribadi (1-5.000 karakter).",
        examples=["Satu sekolah dengan beban administrasi tinggi justru skor DCS rendah."],
    )
    alasan_negatif: str = Field(
        min_length=1,
        max_length=BATAS_TEKS_KASUS,
        description="Mengapa kasus ini tidak sesuai harapan hipotesis (1-5.000 karakter).",
        examples=["Hipotesis memperkirakan beban tinggi menaikkan tuntutan kerja."],
    )
    sumber_ref: str | None = Field(
        default=None,
        max_length=500,
        description="Rujukan sumber kasus (opsional, maks. 500 karakter).",
        examples=["statistik:3f2a9c1e"],
    )

    @model_validator(mode="before")
    @classmethod
    def _abaikan_dibuat_oleh(cls, data: Any) -> Any:
        """Buang `dibuat_oleh` dari body sebelum validasi; nilainya diisi dari token.

        Args:
            data: Body mentah; selain `dict` diteruskan apa adanya ke validasi bawaan.

        Returns:
            Salinan body tanpa kunci `dibuat_oleh` (body lain tidak diubah).
        """
        if isinstance(data, dict) and "dibuat_oleh" in data:
            return {k: v for k, v in data.items() if k != "dibuat_oleh"}
        return data

    @field_validator("ringkasan", "alasan_negatif")
    @classmethod
    def _tidak_hanya_spasi(cls, nilai: str) -> str:
        """Tolak nilai yang hanya berisi spasi; nilai dikembalikan apa adanya (tanpa strip).

        Raises:
            ValueError: Nilai kosong setelah spasi di tepi dibuang (422).
        """
        if not nilai.strip():
            raise ValueError("Tidak boleh kosong.")
        return nilai


class RisetKasusNegatifRead(BaseModel):
    """Satu kasus negatif riset lengkap."""

    id: str = Field(description="ID kasus negatif (UUID v4).")
    protokol_id: str = Field(description="ID protokol riset `TERKUNCI` tempat kasus dicatat.")
    ringkasan: str
    alasan_negatif: str
    sumber_ref: str | None
    dibuat_oleh: str = Field(description="Subjek token pencatat; tidak pernah dari body.")
    created_at: datetime
