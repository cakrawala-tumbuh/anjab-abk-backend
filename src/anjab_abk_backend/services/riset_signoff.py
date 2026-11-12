"""SEAM akses data sign-off PI/etik protokol riset. Append-only: tanpa sunting/hapus/ganti."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from ..errors import ConflictError, NotFoundError, ValidationAppError
from ..schemas.riset_signoff import SignoffRead


class SignoffSudahAdaError(ConflictError):
    """409: protokol itu sudah punya sign-off (`SIGNOFF_SUDAH_ADA`)."""

    error_code = "SIGNOFF_SUDAH_ADA"


class SignoffTakAdaError(NotFoundError):
    """404: protokol belum punya sign-off (`SIGNOFF_TAK_ADA`)."""

    error_code = "SIGNOFF_TAK_ADA"


class LampiranBukanPdfError(ValidationAppError):
    """422: berkas bukan PDF (content-type atau byte awal salah) (`LAMPIRAN_BUKAN_PDF`)."""

    error_code = "LAMPIRAN_BUKAN_PDF"


class LampiranTerlaluBesarError(ValidationAppError):
    """422: ukuran lampiran melebihi `riset_signoff_max_bytes` (`LAMPIRAN_TERLALU_BESAR`)."""

    error_code = "LAMPIRAN_TERLALU_BESAR"


@dataclass(frozen=True)
class LampiranSignoff:
    """Byte PDF lampiran beserta nama dan hash-nya untuk diunduh."""

    nama: str
    isi: bytes
    sha256: str


class RisetSignoffService(Protocol):
    """Kontrak penyimpanan sign-off PI/etik."""

    def create(
        self,
        protokol_id: str,
        *,
        pi_nama: str,
        tanggal_persetujuan_etik: date,
        nomor_persetujuan_etik: str | None,
        lampiran_nama: str,
        content_type: str | None,
        isi: bytes,
        maks_bytes: int,
        dicatat_oleh: str,
    ) -> SignoffRead:
        """Catat sign-off satu kali.

        Raises:
            NotFoundError: Protokol tak ada (404).
            ProtokolBelumTerkunciError: Protokol masih `DRAF` (409).
            SignoffSudahAdaError: Sudah ada sign-off (409).
            LampiranBukanPdfError: Bukan PDF (422).
            LampiranTerlaluBesarError: Melebihi `maks_bytes` (422).
            ValidationAppError: Tanggal di masa depan (422).
        """
        ...

    def get(self, protokol_id: str) -> SignoffRead:
        """Metadata sign-off; 404 bila protokol tak ada, `SignoffTakAdaError` bila belum dicatat."""
        ...

    def lampiran(self, protokol_id: str) -> LampiranSignoff:
        """Byte PDF sign-off; galat sama dengan `get`."""
        ...
