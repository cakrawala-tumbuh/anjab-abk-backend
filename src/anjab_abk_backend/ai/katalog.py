"""Katalog fungsi AI dan pendaftarannya dari env ``AI_FUNGSI_AKTIF``.

Katalog memuat definisi yang tersedia di kode; registri ``FUNGSI_TERDAFTAR``
hanya berisi fungsi yang disebut operator. Bawaan kosong, sehingga tanpa env
tidak ada fungsi AI yang dapat diajukan.
"""

from __future__ import annotations

from ..config import Settings
from .fungsi_p01 import FUNGSI_P01
from .fungsi_p09 import FUNGSI_P09
from .fungsi_p10 import FUNGSI_P10
from .gateway import FUNGSI_TERDAFTAR, FungsiAi

__all__ = ["KATALOG_FUNGSI", "daftarkan_fungsi"]

KATALOG_FUNGSI: dict[str, FungsiAi] = {"P01": FUNGSI_P01, "P09": FUNGSI_P09, "P10": FUNGSI_P10}
"""Semua fungsi AI yang tersedia di kode, menurut kode."""


def daftarkan_fungsi(settings: Settings) -> None:
    """Isi ``FUNGSI_TERDAFTAR`` tepat sesuai ``settings.ai_fungsi_aktif``.

    Idempoten. Objek registri diubah di tempat (bukan diganti) agar modul yang
    sudah mengimpornya melihat isi terbaru. Env kosong mengosongkan registri.

    Args:
        settings: Pengaturan aplikasi.

    Raises:
        ValueError: ada kode di ``ai_fungsi_aktif`` yang tidak ada di katalog;
            registri tidak diubah.
    """
    tak_dikenal = [k for k in settings.ai_fungsi_aktif if k not in KATALOG_FUNGSI]
    if tak_dikenal:
        raise ValueError(
            f"AI_FUNGSI_AKTIF memuat kode tak dikenal: {', '.join(tak_dikenal)}. "
            f"Tersedia: {', '.join(sorted(KATALOG_FUNGSI)) or '-'}."
        )
    FUNGSI_TERDAFTAR.clear()
    for kode in settings.ai_fungsi_aktif:
        FUNGSI_TERDAFTAR[kode] = KATALOG_FUNGSI[kode]
