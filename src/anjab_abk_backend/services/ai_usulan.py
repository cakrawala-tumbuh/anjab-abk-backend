"""SEAM pengajuan fungsi AI non-narasi atas satu sasaran, dengan hasil disimpan sebagai usulan."""

from __future__ import annotations

from typing import Any, Protocol

from ..ai.redaksi import SumberAi
from ..errors import ConflictError
from ..schemas.ai_usulan import AiUsulanRingkas, SasaranUsulan
from ..security import Principal

__all__ = [
    "AiUsulanService",
    "FungsiAiBelumAktifError",
    "PiiModeAiBelumDidukungError",
    "UsulanBerjalanError",
]


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
