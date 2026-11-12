"""SEAM register klarifikasi narasi. Sengaja TIDAK punya update umum maupun delete.

Setiap aksi (buat, persetujuan, jawaban, batalkan) menambah satu baris riwayat append-only
dalam transaksi yang sama. Kode galat huruf besar mengikuti kontrak klien web.
"""

from __future__ import annotations

from typing import Protocol

from ...errors import ConflictError, ValidationAppError
from ...schemas.common import ErrorDetail
from ..schemas.klarifikasi import (
    BatalkanKlarifikasi,
    Disposition,
    JawabanKlarifikasi,
    KlarifikasiCreate,
    KlarifikasiDariUsulan,
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
    """409: aksi ditolak karena pertanyaan sudah `TERJAWAB`, `DIBATALKAN`, atau `DITOLAK`."""

    error_code = "KLARIFIKASI_TIDAK_TERBUKA"

    def __init__(self, disposition: Disposition) -> None:
        """Susun pesan dari disposisi saat ini."""
        super().__init__(f"Klarifikasi berstatus {disposition.value}; aksi ditolak.")


class UsulanBukanP04Error(ValidationAppError):
    """422: usulan bukan keluaran P04 atau sasarannya bukan kasus narasi."""

    error_code = "USULAN_BUKAN_P04"


class UsulanBelumDiterimaError(ConflictError):
    """409: putusan terakhir usulan bukan `APPROVE`/`REVISE` (atau belum ada putusan)."""

    error_code = "USULAN_BELUM_DITERIMA"


class UsulanTidakMaterialError(ValidationAppError):
    """422: usulan P04 menyatakan tidak material atau tidak berisi pertanyaan."""

    error_code = "USULAN_TIDAK_MATERIAL"


class PeriodeTakAdaError(ValidationAppError):
    """422: periode tidak terbaca dari parameter run usulan maupun kasus sasarannya."""

    error_code = "PERIODE_TAK_ADA"


class IsianUsulanKurangError(ValidationAppError):
    """422: isi usulan P04 tak cukup untuk mengisi field wajib register."""

    error_code = "ISIAN_USULAN_KURANG"


class UsulanSudahDiterapkanError(ConflictError):
    """409: usulan ini sudah menjadi baris register; `details[0].msg` memuat id klarifikasi.

    Klien membaca id yang sudah ada dari `details[0]` (`code` = `USULAN_SUDAH_DITERAPKAN`,
    `loc` = `["klarifikasi_id"]`, `msg` = id klarifikasi).
    """

    error_code = "USULAN_SUDAH_DITERAPKAN"

    def __init__(self, klarifikasi_id: str | None) -> None:
        """Bangun galat dengan rincian id klarifikasi yang sudah ada (bila diketahui).

        Args:
            klarifikasi_id: Id hasil penerapan sebelumnya; None bila tak terbaca (mis.
                bentrok UNIQUE dari permintaan bersamaan yang belum terlihat).
        """
        super().__init__(
            "Usulan ini sudah diterapkan menjadi klarifikasi.",
            details=(
                [
                    ErrorDetail(
                        loc=["klarifikasi_id"],
                        msg=klarifikasi_id,
                        type="conflict",
                        code=self.error_code,
                    )
                ]
                if klarifikasi_id
                else None
            ),
        )


class KlarifikasiService(Protocol):
    """Kontrak penyimpanan register klarifikasi dan riwayatnya."""

    def create(self, data: KlarifikasiCreate, *, dibuat_oleh: str) -> KlarifikasiDetail:
        """Simpan pertanyaan `MENUNGGU`/`TERBUKA` + event `DIBUAT`.

        Raises:
            NotFoundError: Kasus narasi tak ada (404).
            KlarifikasiGandaError: Sudah ada yang `TERBUKA` untuk klaim itu (409).
        """
        ...

    def dari_usulan(
        self, ai_usulan_id: str, data: KlarifikasiDariUsulan, *, dibuat_oleh: str
    ) -> KlarifikasiDetail:
        """Terapkan usulan P04 yang diterima menjadi SATU baris register (tepat sekali).

        Raises:
            NotFoundError: Usulan atau kasus sasarannya tak ada (404).
            UsulanBukanP04Error: Bukan usulan P04 atas kasus narasi (422).
            UsulanBelumDiterimaError: Putusan terakhir bukan APPROVE/REVISE (409).
            UsulanTidakMaterialError: Tidak material / tanpa pertanyaan (422).
            PeriodeTakAdaError: Periode tak terbaca (422).
            IsianUsulanKurangError: `preferred_role`/`why_ask` kosong tanpa penggantinya (422).
            UsulanSudahDiterapkanError: Usulan sudah diterapkan (409).
            KlarifikasiGandaError: Sudah ada klarifikasi `TERBUKA` untuk klaim itu (409).
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
        """Setujui/tolak pertanyaan `TERBUKA` yang `MENUNGGU`; `TOLAK` menutup baris (`DITOLAK`).

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
            KlarifikasiTidakTerbukaError: Sudah `TERJAWAB`/`DIBATALKAN`/`DITOLAK` (409).
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
