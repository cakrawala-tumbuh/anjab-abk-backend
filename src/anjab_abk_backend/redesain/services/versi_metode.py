"""SEAM akses data catatan versi metode redesain (sheet PERUBAHAN)."""

from __future__ import annotations

from typing import Protocol

from ...schemas.search import Domain, Order
from ..schemas.versi_metode import VersiMetodeCreate, VersiMetodeRead, VersiMetodeUpdate

SEARCHABLE_FIELDS = frozenset({"id", "versi", "bagian"})
"""Field yang boleh dipakai pada domain search catatan versi metode."""


class VersiMetodeService(Protocol):
    """Kontrak catatan versi metode. Sengaja TIDAK punya `delete`."""

    def create(self, data: VersiMetodeCreate, *, pelaku_kode_orang: str | None) -> VersiMetodeRead:
        """Buat catatan dan catat riwayat.

        Raises:
            ConflictError: pasangan `versi`+`bagian` sudah ada (409).
        """
        ...

    def get(self, versi_id: str) -> VersiMetodeRead:
        """Ambil satu catatan; `NotFoundError` bila tak ada."""
        ...

    def list(self, *, limit: int, offset: int) -> tuple[list[VersiMetodeRead], int]:
        """Daftar berurutan menurut tanggal, versi, lalu bagian."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[VersiMetodeRead], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`)."""
        ...

    def update(
        self, versi_id: str, data: VersiMetodeUpdate, *, pelaku_kode_orang: str | None
    ) -> VersiMetodeRead:
        """Ubah parsial dan catat riwayat.

        Raises:
            NotFoundError: catatan tidak ada.
            ConflictError: perubahan membuat pasangan `versi`+`bagian` bentrok (409).
        """
        ...
