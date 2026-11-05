"""Skema pengaturan penyedia model AI. Tidak pernah memuat kredensial utuh di keluaran."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ..ai.penyedia import AiEffort, AiPenyediaMode

__all__ = [
    "AiPenyediaAksi",
    "AiPenyediaKredensialHapus",
    "AiPenyediaKredensialPasang",
    "AiPenyediaModeUbah",
    "AiPenyediaModelUbah",
    "AiPenyediaRead",
    "AiPenyediaStatusRead",
]

_PANJANG_KUNCI_MIN = 20


class AiPenyediaAksi(StrEnum):
    """Aksi pada event pengaturan penyedia AI."""

    UBAH_MODE = "UBAH_MODE"
    UBAH_MODEL = "UBAH_MODEL"
    PASANG_KREDENSIAL = "PASANG_KREDENSIAL"
    HAPUS_KREDENSIAL = "HAPUS_KREDENSIAL"


class AiPenyediaStatusRead(BaseModel):
    """Status pengaturan penyedia AI yang berlaku."""

    mode: AiPenyediaMode = Field(description="Penyedia terpilih; MATI bila belum diatur.")
    model: str = Field(description="Model efektif (bawaan bila belum diubah).")
    effort: AiEffort = Field(description="Effort efektif (bawaan bila belum diubah).")
    kredensial_terpasang: bool = Field(description="True bila kunci API tersimpan.")
    kredensial_akhiran: str | None = Field(
        default=None, description="Empat karakter terakhir kunci API."
    )
    kredensial_terbaca: bool = Field(
        description="True bila kunci tersimpan dapat didekripsi dengan kunci induk saat ini."
    )
    enkripsi_siap: bool = Field(description="True bila kunci induk deployment sah.")
    diperbarui_oleh: str | None = Field(default=None, description="Aktor perubahan terakhir.")
    pada: datetime | None = Field(default=None, description="Waktu perubahan terakhir (UTC).")


class _AlasanAksi(BaseModel):
    """Body dasar aksi penyedia. Aktor tidak pernah dibaca dari body (diambil dari token)."""

    model_config = ConfigDict(extra="forbid")

    alasan: str = Field(
        min_length=5,
        max_length=2000,
        description="Alasan aksi (min. 5 karakter).",
        examples=["Beralih penyedia untuk evaluasi"],
    )


class AiPenyediaModeUbah(_AlasanAksi):
    """Body ``POST .../penyedia/mode``."""

    mode: AiPenyediaMode = Field(description="Penyedia baru. Memilih tidak menyalakan AI.")


class AiPenyediaModelUbah(_AlasanAksi):
    """Body ``POST .../penyedia/model``. ``null`` mengembalikan nilai ke bawaan.

    Kedua field wajib dikirim supaya field yang lupa disertakan tidak diam-diam mereset
    nilai yang berlaku. ``model`` sengaja tanpa batasan bentuk di sini: nama yang tidak sah
    ditolak service dengan kode ``MODEL_DITOLAK``.
    """

    model: str | None = Field(description="Nama model, atau null untuk bawaan.")
    effort: AiEffort | None = Field(description="Effort, atau null untuk bawaan.")


class AiPenyediaKredensialPasang(_AlasanAksi):
    """Body ``POST .../penyedia/kredensial``. Nilai kunci tidak pernah keluar lagi."""

    kunci_api: SecretStr = Field(
        min_length=_PANJANG_KUNCI_MIN,
        description="Kunci API Anthropic (min. 20 karakter). Hanya dapat ditulis.",
    )

    @field_validator("kunci_api", mode="after")
    @classmethod
    def _panjang_setelah_strip(cls, nilai: SecretStr) -> SecretStr:
        """Tolak kunci yang baru mencapai 20 karakter karena spasi pengapit.

        Service menyimpan nilai hasil ``strip``, sehingga panjangnya dihitung atas nilai itu.
        Pesan galatnya tidak memuat nilai masukan.
        """
        if len(nilai.get_secret_value().strip()) < _PANJANG_KUNCI_MIN:
            raise ValueError("Kunci API terlalu pendek.")
        return nilai


class AiPenyediaKredensialHapus(_AlasanAksi):
    """Body ``POST .../penyedia/kredensial/hapus``."""


class AiPenyediaRead(BaseModel):
    """Respons pengaturan penyedia AI. Tanpa kredensial maupun identitas akun."""

    model_config = ConfigDict(protected_namespaces=())

    mode: AiPenyediaMode = Field(description="Penyedia terpilih; MATI bila belum diatur.")
    mode_tersedia: list[AiPenyediaMode] = Field(description="Semua mode yang dapat dipilih.")
    kredensial_terpasang: bool = Field(description="True bila kunci API tersimpan.")
    kredensial_akhiran: str | None = Field(
        default=None, description="Empat karakter terakhir kunci API."
    )
    kredensial_terbaca: bool = Field(
        description="True bila kunci tersimpan dapat didekripsi; false bila tidak ada kunci."
    )
    enkripsi_siap: bool = Field(description="True bila kunci induk deployment sah.")
    model: str = Field(description="Model efektif.")
    effort: AiEffort = Field(description="Effort efektif.")
    effort_tersedia: list[AiEffort] = Field(description="Semua effort yang dapat dipilih.")
    model_bawaan: str = Field(description="Model bila pengaturan kosong.")
    effort_bawaan: AiEffort = Field(description="Effort bila pengaturan kosong.")
    diperbarui_oleh: str | None = Field(default=None, description="Aktor perubahan terakhir.")
    diperbarui_pada: datetime | None = Field(
        default=None, description="Waktu perubahan terakhir (UTC)."
    )
    langganan_cli_terpasang: bool = Field(description="True bila binary CLI langganan ada.")
    langganan_cli_masuk: bool = Field(description="True bila CLI langganan sudah masuk.")
    langganan_cli_versi: str | None = Field(default=None, description="Versi CLI langganan.")
    inference_geo: str = Field(
        description="Nilai env AI_INFERENCE_GEO, baca-saja; kosong bila tidak diatur."
    )
    refusal_fallback: bool = Field(description="Nilai env AI_REFUSAL_FALLBACK, baca-saja.")
