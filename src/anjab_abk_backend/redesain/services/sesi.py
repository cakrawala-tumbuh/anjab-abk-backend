"""SEAM akses data sesi partisipasi redesain (sheet SESI; BUKAN Time Study)."""

from __future__ import annotations

from typing import Protocol

from ...schemas.search import Domain, Order
from ..schemas.sesi import RekapOrangRead, SesiCreate, SesiRead, SesiUpdate

SEARCHABLE_FIELDS = frozenset({"kode_sesi", "kode_orang", "jenis_kegiatan", "status_izin"})
"""Field yang boleh dipakai pada domain search sesi."""


class SesiService(Protocol):
    """Kontrak sesi partisipasi. Sengaja TIDAK punya `delete` dan tanpa gerbang izin."""

    def create(self, data: SesiCreate, *, pelaku_kode_orang: str | None) -> SesiRead:
        """Catat keterlibatan satu orang × satu sesi dan riwayatnya.

        Raises:
            ValidationAppError: kode orang/sekolah/masalah tak dikenal (422).
            ConflictError: pasangan `kode_sesi`+`kode_orang` sudah ada (409).
        """
        ...

    def get(self, sesi_id: str) -> SesiRead:
        """Ambil satu baris sesi; `NotFoundError` bila tak ada."""
        ...

    def list(self, *, limit: int, offset: int) -> tuple[list[SesiRead], int]:
        """Daftar berurutan menurut `kode_sesi`, lalu `kode_orang`."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[SesiRead], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`)."""
        ...

    def update(self, sesi_id: str, data: SesiUpdate, *, pelaku_kode_orang: str | None) -> SesiRead:
        """Ubah parsial (tautan masalah ganti-penuh bila dikirim) dan catat riwayat."""
        ...

    def rekap_orang(self, *, limit: int, offset: int) -> tuple[list[RekapOrangRead], int]:
        """Rekap per `kode_orang`: jumlah sesi berbeda & total menit (NULL diabaikan)."""
        ...
