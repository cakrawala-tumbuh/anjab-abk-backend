"""SEAM register klarifikasi narasi. Sengaja TIDAK punya update umum maupun delete.

Setiap aksi (buat, persetujuan, jawaban, batalkan) menambah satu baris riwayat append-only
dalam transaksi yang sama. Kode galat huruf besar mengikuti kontrak klien web.
"""

from __future__ import annotations

from typing import Protocol

from ...errors import ConflictError
from ..schemas.klarifikasi import (
    BatalkanKlarifikasi,
    Disposition,
    JawabanKlarifikasi,
    KlarifikasiCreate,
    KlarifikasiDetail,
    KlarifikasiRead,
    PersetujuanKlarifikasi,
)


class KlarifikasiGandaError(ConflictError):
    """409: sudah ada klarifikasi `TERBUKA` untuk kasus dan klaim yang sama."""

    error_code = "KLARIFIKASI_GANDA"


class ReviewerTidakIndependenError(ConflictError):
    """409: pembuat pertanyaan mencoba memutuskan persetujuannya sendiri."""

    error_code = "REVIEWER_TIDAK_INDEPENDEN"


class PersetujuanSudahAdaError(ConflictError):
    """409: pertanyaan sudah diputus (`DISETUJUI`/`DITOLAK`)."""

    error_code = "PERSETUJUAN_SUDAH_ADA"


class KlarifikasiBelumDisetujuiError(ConflictError):
    """409: jawaban dicatat sebelum reviewer menyetujui pertanyaan."""

    error_code = "KLARIFIKASI_BELUM_DISETUJUI"


class KlarifikasiTidakTerbukaError(ConflictError):
    """409: aksi ditolak karena pertanyaan sudah `TERJAWAB` atau `DIBATALKAN`."""

    error_code = "KLARIFIKASI_TIDAK_TERBUKA"

    def __init__(self, disposition: Disposition) -> None:
        """Susun pesan dari disposisi saat ini."""
        super().__init__(f"Klarifikasi berstatus {disposition.value}; aksi ditolak.")


class KlarifikasiService(Protocol):
    """Kontrak penyimpanan register klarifikasi dan riwayatnya."""

    def create(self, data: KlarifikasiCreate, *, dibuat_oleh: str) -> KlarifikasiDetail:
        """Simpan pertanyaan `MENUNGGU`/`TERBUKA` + event `DIBUAT`.

        Raises:
            NotFoundError: Kasus narasi tak ada (404).
            KlarifikasiGandaError: Sudah ada yang `TERBUKA` untuk klaim itu (409).
        """
        ...

    def get(self, klarifikasi_id: str) -> KlarifikasiDetail:
        """Ambil satu pertanyaan beserta `riwayat`; `NotFoundError` bila tak ada."""
        ...

    def daftar(
        self,
        *,
        narasi_id: str | None,
        disposition: Disposition | None,
        limit: int,
        offset: int,
    ) -> tuple[list[KlarifikasiRead], int]:
        """Daftar pertanyaan (terbaru dulu) dengan filter opsional."""
        ...

    def putuskan(
        self, klarifikasi_id: str, data: PersetujuanKlarifikasi, *, reviewer: str
    ) -> KlarifikasiDetail:
        """Setujui/tolak pertanyaan `TERBUKA` yang `MENUNGGU`.

        Raises:
            NotFoundError: Tak ada (404).
            KlarifikasiTidakTerbukaError: Bukan `TERBUKA` (409).
            PersetujuanSudahAdaError: Sudah diputus (409).
            ReviewerTidakIndependenError: `reviewer` = pembuat (409).
        """
        ...

    def catat_jawaban(
        self, klarifikasi_id: str, data: JawabanKlarifikasi, *, pencatat: str
    ) -> KlarifikasiDetail:
        """Catat jawaban mentah; disposisi menjadi `TERJAWAB`.

        Raises:
            NotFoundError: Tak ada (404).
            KlarifikasiTidakTerbukaError: Sudah `TERJAWAB`/`DIBATALKAN` (409).
            KlarifikasiBelumDisetujuiError: Belum `DISETUJUI` (409).
        """
        ...

    def batalkan(
        self, klarifikasi_id: str, data: BatalkanKlarifikasi, *, pembatal: str
    ) -> KlarifikasiDetail:
        """Batalkan pertanyaan `TERBUKA`; disposisi menjadi `DIBATALKAN`.

        Raises:
            NotFoundError: Tak ada (404).
            KlarifikasiTidakTerbukaError: Bukan `TERBUKA` (409).
        """
        ...
