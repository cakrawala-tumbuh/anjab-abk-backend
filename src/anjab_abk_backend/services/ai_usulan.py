"""SEAM pengajuan fungsi AI non-narasi atas satu sasaran, dengan hasil disimpan sebagai usulan."""

from __future__ import annotations

from typing import Any, Protocol

from ..ai.redaksi import SumberAi
from ..errors import ConflictError
from ..schemas.ai_usulan import AiUsulanRead, AiUsulanRingkas, SasaranUsulan
from ..schemas.search import Domain, Order
from ..security import Principal

__all__ = [
    "SEARCHABLE_FIELDS",
    "AiUsulanService",
    "FungsiAiBelumAktifError",
    "PiiModeAiBelumDidukungError",
    "UsulanBerjalanError",
]

SEARCHABLE_FIELDS = frozenset(
    {"fungsi", "sasaran_jenis", "sasaran_id", "hasil_serap", "created_at"}
)
"""Field yang boleh dipakai pada domain search usulan AI; `isi` dan `amplop` tidak termasuk."""


class PiiModeAiBelumDidukungError(ConflictError):
    """409: `AI_PII_MODE` bukan `BLOKIR` (mode `SAMARKAN` belum dibuka)."""

    error_code = "pii_mode_belum_didukung"


class UsulanBerjalanError(ConflictError):
    """409: sasaran dan fungsi yang sama masih punya usulan yang belum diserap."""

    error_code = "usulan_berjalan"


class FungsiAiBelumAktifError(ConflictError):
    """409: fungsi belum terdaftar (`AI_FUNGSI_AKTIF`)."""

    error_code = "fungsi_belum_aktif"


class AiUsulanService(Protocol):
    """Kontrak tabel `ai_usulan`: pengajuan umum fungsi AI non-narasi."""

    def ajukan(
        self,
        fungsi: str,
        sasaran_jenis: SasaranUsulan,
        sasaran_id: str,
        sumber: list[SumberAi],
        parameter: dict[str, Any],
        principal: Principal,
    ) -> AiUsulanRingkas:
        """Periksa gerbang, ajukan job lewat gateway, dan catat satu usulan."""
        ...

    def get(self, usulan_id: str) -> AiUsulanRead:
        """Ambil satu usulan lengkap dengan `isi`/`amplop`; `NotFoundError` (404) bila tak ada."""
        ...

    def list(
        self,
        *,
        fungsi: str | None,
        sasaran_jenis: str | None,
        sasaran_id: str | None,
        hasil_serap: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AiUsulanRingkas], int]:
        """Daftar ringkas (tanpa `isi`/`amplop`), terbaru dulu, dengan filter opsional."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[AiUsulanRingkas], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`); hasil tanpa `isi`/`amplop`."""
        ...
