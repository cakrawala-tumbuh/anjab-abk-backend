"""SEAM akses data statistik riset. Sengaja TIDAK punya update/delete umum.

Satu-satunya perubahan baris yang sah adalah `verifikasi()` (DRAF -> TERVERIFIKASI), sekali
saja dan hanya oleh subjek yang bukan pengunggahnya. Koreksi statistik = baris baru.
"""

from __future__ import annotations

from typing import Protocol

from ..errors import ConflictError
from ..schemas.riset_statistik import RisetStatistikCreate, RisetStatistikRead


class ProtokolBelumTerkunciError(ConflictError):
    """409: protokol masih `DRAF`, sehingga belum boleh menjadi dasar statistik."""

    error_code = "PROTOKOL_BELUM_TERKUNCI"


class StatistikSudahTerverifikasiError(ConflictError):
    """409: statistik sudah `TERVERIFIKASI`; verifikasi tidak bisa diulang."""

    error_code = "STATISTIK_SUDAH_TERVERIFIKASI"


class PemverifikasiTidakIndependenError(ConflictError):
    """409: subjek pemverifikasi sama dengan pengunggah (`dibuat_oleh`)."""

    error_code = "PEMVERIFIKASI_TIDAK_INDEPENDEN"


class RisetStatistikService(Protocol):
    """Kontrak penyimpanan statistik riset per protokol terkunci."""

    def create(
        self, protokol_id: str, data: RisetStatistikCreate, *, dibuat_oleh: str
    ) -> RisetStatistikRead:
        """Simpan statistik `DRAF` baru untuk protokol `TERKUNCI`.

        Raises:
            NotFoundError: Protokol tak ada (404).
            ProtokolBelumTerkunciError: Protokol masih `DRAF` (409 `PROTOKOL_BELUM_TERKUNCI`).
        """
        ...

    def list_by_protokol(
        self, protokol_id: str, *, status: str | None, limit: int, offset: int
    ) -> tuple[list[RisetStatistikRead], int]:
        """Daftar statistik satu protokol, terbaru dulu, filter `status` opsional.

        Raises:
            NotFoundError: Protokol tak ada (404).
        """
        ...

    def verifikasi(self, statistik_id: str, *, diverifikasi_oleh: str) -> RisetStatistikRead:
        """Set `TERVERIFIKASI` beserta pemverifikasi dan waktunya.

        Raises:
            NotFoundError: Statistik tak ada (404).
            StatistikSudahTerverifikasiError: Sudah terverifikasi (409).
            PemverifikasiTidakIndependenError: Pemverifikasi = pengunggah (409).
        """
        ...
