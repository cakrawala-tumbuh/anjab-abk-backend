"""SEAM metrik alur narasi: pencatatan detak menit aktif dan agregat metrik (hanya baca)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Protocol

from ...errors import ValidationAppError
from ..schemas.kasus import NarrativeKind
from ..schemas.metrik import BATAS_RENTANG_HARI, MetrikNarasiRead


class RentangMetrikTidakValidError(ValidationAppError):
    """422: `dari` > `sampai`, atau rentang melebihi `BATAS_RENTANG_HARI` hari."""

    error_code = "rentang_metrik_tidak_valid"


def periksa_rentang(dari: date, sampai: date) -> None:
    """Pastikan rentang tanggal sah.

    Args:
        dari: Tanggal awal (inklusif).
        sampai: Tanggal akhir (inklusif).

    Raises:
        RentangMetrikTidakValidError: Bila `dari` > `sampai` atau rentang > 366 hari.
    """
    if dari > sampai:
        raise RentangMetrikTidakValidError("`dari` tidak boleh melebihi `sampai`.")
    if (sampai - dari).days + 1 > BATAS_RENTANG_HARI:
        raise RentangMetrikTidakValidError(f"Rentang paling panjang {BATAS_RENTANG_HARI} hari.")


def potong_ke_menit(waktu: datetime) -> datetime:
    """Potong `waktu` ke awal menit (UTC), buang detik dan mikrodetik."""
    return waktu.astimezone(UTC).replace(second=0, microsecond=0)


class NarasiMetrikService(Protocol):
    """Pencatatan menit aktif dan perhitungan metrik agregat alur narasi."""

    def catat_menit_aktif(
        self, narasi_id: str, actor_key: str, sekarang: datetime | None = None
    ) -> None:
        """Catat satu detak aktif; idempoten per (kasus, aktor, menit).

        Args:
            narasi_id: Id kasus narasi.
            actor_key: Subjek token pemanggil.
            sekarang: Waktu acuan (hanya untuk uji); bawaan jam server.

        Raises:
            NotFoundError: Kasus tidak ada.
        """
        ...

    def hitung(
        self, dari: date, sampai: date, narrative_kind: NarrativeKind | None = None
    ) -> MetrikNarasiRead:
        """Hitung metrik pada rentang `dari`..`sampai` (inklusif, hari UTC).

        Args:
            dari: Tanggal awal.
            sampai: Tanggal akhir.
            narrative_kind: Saring per jenis narasi kasus; None = semua.

        Returns:
            Metrik agregat; rasio berpenyebut nol bernilai None.

        Raises:
            RentangMetrikTidakValidError: Rentang tidak sah.
        """
        ...
