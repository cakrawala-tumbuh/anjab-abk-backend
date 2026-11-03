"""Registri feature flag fungsional (fail-closed) dan pemeriksa statusnya.

Nilai flag dibaca dari `Settings` (env `FEATURE_<KODE>`), default mati. Service/router
lain WAJIB memakai `fitur_aktif` / `require_fitur`, tidak membaca `Settings` langsung.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends

from .config import Settings, get_settings
from .errors import ConflictError
from .schemas.common import FiturKode, FiturRead

__all__ = [
    "FiturKode",
    "FiturNonaktifError",
    "daftar_fitur",
    "fitur_aktif",
    "require_fitur",
]

KETERANGAN: dict[FiturKode, str] = {
    FiturKode.AI_NARRATIVE_DRAFT: "Draf narasi yang dibantu AI.",
    FiturKode.PARTICIPANT_VALIDATION: "Validasi hasil oleh partisipan.",
    FiturKode.WCP_DCS_SCORING: "Skor dan interpretasi WCP/DCS.",
    FiturKode.RESEARCH_EXPORT: "Ekspor data riset. Belum ada fungsi yang digerbang.",
    FiturKode.CHANGE_AUTHORIZATION: (
        "Otorisasi keputusan perubahan. Belum ada fungsi yang digerbang."
    ),
}
"""Keterangan tiap flag, dipakai respons status."""


class FiturNonaktifError(ConflictError):
    """Fungsi yang diminta sedang dimatikan oleh feature flag (HTTP 409)."""

    error_code = "feature_disabled"

    def __init__(self, kode: FiturKode) -> None:
        super().__init__(f"Fungsi {kode.value} sedang dinonaktifkan (feature flag).")
        self.kode = kode


def fitur_aktif(kode: FiturKode, settings: Settings | None = None) -> bool:
    """Kembalikan True bila flag `kode` hidup.

    Args:
        kode: Kode fungsi yang diperiksa.
        settings: Settings yang dipakai; default singleton `get_settings()`.

    Returns:
        Nilai field `feature_<kode huruf kecil>` pada settings.
    """
    cfg = settings or get_settings()
    return bool(getattr(cfg, f"feature_{kode.value.lower()}"))


def daftar_fitur(settings: Settings | None = None) -> list[FiturRead]:
    """Kembalikan status kelima flag, berurutan sesuai enum `FiturKode`."""
    return [
        FiturRead(kode=k, aktif=fitur_aktif(k, settings), keterangan=KETERANGAN[k])
        for k in FiturKode
    ]


def require_fitur(kode: FiturKode) -> Callable[..., None]:
    """Bangun dependency FastAPI yang menolak request bila flag `kode` mati.

    Args:
        kode: Kode fungsi yang digerbang.

    Returns:
        Dependency yang melempar `FiturNonaktifError` (409, `feature_disabled`)
        saat flag mati dan tidak melakukan apa pun saat hidup.
    """

    def _dependency(settings: Annotated[Settings, Depends(get_settings)]) -> None:
        if not fitur_aktif(kode, settings):
            raise FiturNonaktifError(kode)

    return _dependency
