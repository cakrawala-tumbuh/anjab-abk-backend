"""SEAM akses data alternatif redesain (sheet ALTERNATIF)."""

from __future__ import annotations

from typing import Protocol

from ...schemas.search import Domain, Order
from ..schemas.alternatif import AlternatifCreate, AlternatifRead, AlternatifUpdate

SEARCHABLE_FIELDS = frozenset({"id", "kode", "masalah_id", "opsi", "status_telaah"})
"""Field yang boleh dipakai pada domain search alternatif."""


class AlternatifService(Protocol):
    """Kontrak alternatif redesain. Sengaja TIDAK punya `delete`."""

    def create(self, data: AlternatifCreate, *, pelaku_kode_orang: str | None) -> AlternatifRead:
        """Buat alternatif (kode `U-NNN` dibangkitkan) dan catat riwayat.

        Raises:
            ValidationAppError: masalah/jabatan/kode orang tak dikenal, atau aturan
                opsi/status dilanggar (422).
            ConflictError: kode hasil bangkitan bentrok (409).
        """
        ...

    def get(self, alternatif_id: str) -> AlternatifRead:
        """Ambil satu alternatif; `NotFoundError` bila tak ada."""
        ...

    def list(self, *, limit: int, offset: int) -> tuple[list[AlternatifRead], int]:
        """Daftar berurutan menurut `kode`."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[AlternatifRead], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`)."""
        ...

    def update(
        self, alternatif_id: str, data: AlternatifUpdate, *, pelaku_kode_orang: str | None
    ) -> AlternatifRead:
        """Ubah parsial dan catat riwayat; aturan divalidasi pada keadaan akhir."""
        ...
