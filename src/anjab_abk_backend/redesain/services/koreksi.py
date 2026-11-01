"""SEAM akses data koreksi langkah ALUR (append-only) & tampilan alur sekolah."""

from __future__ import annotations

from typing import Protocol

from ..schemas.koreksi import AlurRead, KoreksiRead


class KoreksiService(Protocol):
    """Kontrak koreksi langkah. Sengaja TIDAK punya update/delete."""

    def alur_untuk_konfirmasi(self, konfirmasi_id: str, *, kode_orang: str) -> AlurRead:
        """Proses (beserta langkah) milik masalah & sekolah konfirmasi milik `kode_orang`.

        Raises:
            NotFoundError: konfirmasi tak ada (404).
            ForbiddenError: konfirmasi milik orang lain (403).
            ConflictError: `DUGAAN_BELUM_DITAMPILKAN` bila dugaan belum tampil (409).
        """
        ...

    def tambah_oleh_tim(self, langkah_id: str, isi: str, *, kode_orang: str) -> KoreksiRead:
        """Tulis koreksi Tim (`konfirmasi_id` NULL) lalu catat riwayat.

        Raises:
            NotFoundError: langkah tak ada (404).
        """
        ...

    def tambah_oleh_pengisi(
        self, langkah_id: str, isi: str, konfirmasi_id: str | None, *, kode_orang: str
    ) -> KoreksiRead:
        """Tulis koreksi pengisi sekolah lewat konfirmasi miliknya lalu catat riwayat.

        Raises:
            NotFoundError: langkah/konfirmasi tak ada (404).
            ForbiddenError: tanpa `konfirmasi_id`, konfirmasi bukan milik pemanggil, atau
                masalah/sekolah konfirmasi berbeda dari proses langkah itu (403).
            ConflictError: `DUGAAN_BELUM_DITAMPILKAN` (409).
        """
        ...

    def list_by_langkah(
        self, langkah_id: str, *, limit: int, offset: int
    ) -> tuple[list[KoreksiRead], int]:
        """Koreksi sebuah langkah terurut `waktu`; `NotFoundError` bila langkah tak ada."""
        ...
