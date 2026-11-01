"""SEAM akses data bukti redesain (sheet BUKTI)."""

from __future__ import annotations

from typing import Protocol

from ...schemas.search import Domain, Order
from ..schemas.bukti import BuktiCreate, BuktiRead, BuktiUpdate

SEARCHABLE_FIELDS = frozenset(
    {"id", "kode", "masalah_id", "langkah_id", "jenis", "status_pemeriksaan", "independen"}
)
"""Field yang boleh dipakai pada domain search bukti."""


class BuktiService(Protocol):
    """Kontrak bukti redesain. Sengaja TIDAK punya `delete`."""

    def create(self, data: BuktiCreate, *, pelaku_kode_orang: str | None) -> BuktiRead:
        """Buat bukti (kode `B-NNNN` dibangkitkan) dan catat riwayat.

        Raises:
            ValidationAppError: masalah/langkah/kode orang tak dikenal (422).
            ConflictError: kode hasil bangkitan bentrok (409).
        """
        ...

    def get(self, bukti_id: str) -> BuktiRead:
        """Ambil satu bukti; `NotFoundError` bila tak ada."""
        ...

    def list(self, *, limit: int, offset: int) -> tuple[list[BuktiRead], int]:
        """Daftar berurutan menurut `kode`."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[BuktiRead], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`)."""
        ...

    def update(
        self, bukti_id: str, data: BuktiUpdate, *, pelaku_kode_orang: str | None
    ) -> BuktiRead:
        """Ubah parsial dan catat riwayat."""
        ...
