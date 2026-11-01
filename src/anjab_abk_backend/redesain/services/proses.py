"""SEAM akses data proses & langkah redesain (sheet ALUR)."""

from __future__ import annotations

from typing import Protocol

from ...schemas.search import Domain, Order
from ..schemas.proses import (
    LangkahCreate,
    LangkahRead,
    LangkahUpdate,
    ProsesCreate,
    ProsesRead,
    ProsesUpdate,
)

SEARCHABLE_FIELDS = frozenset({"masalah_id", "sekolah_id", "kode"})
"""Field yang boleh dipakai pada domain search proses."""


class ProsesService(Protocol):
    """Kontrak proses & langkah redesain. Sengaja TIDAK punya `delete`."""

    def create(self, data: ProsesCreate, *, pelaku_kode_orang: str | None) -> ProsesRead:
        """Buat proses (kode `P-NNN` dibangkitkan global) lalu catat riwayat.

        Raises:
            ValidationAppError: masalah/sekolah tak dikenal, atau sekolah berbeda dari
                `masalah.sekolah_id` yang terisi (422).
            ConflictError: kode hasil bangkitan bentrok (409).
        """
        ...

    def get(self, proses_id: str) -> ProsesRead:
        """Ambil satu proses beserta langkahnya; `NotFoundError` bila tak ada."""
        ...

    def list(self, *, limit: int, offset: int) -> tuple[list[ProsesRead], int]:
        """Daftar berurutan menurut `kode`."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[ProsesRead], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`)."""
        ...

    def update(
        self, proses_id: str, data: ProsesUpdate, *, pelaku_kode_orang: str | None
    ) -> ProsesRead:
        """Ubah parsial proses (aturan sekolah↔masalah divalidasi ulang) dan catat riwayat."""
        ...

    def tambah_langkah(
        self, proses_id: str, data: LangkahCreate, *, pelaku_kode_orang: str | None
    ) -> LangkahRead:
        """Tambah langkah (kode `<kode proses>-SNN`) pada proses lalu catat riwayat.

        Raises:
            NotFoundError: proses tidak ada (404).
            ConflictError: kode langkah hasil bangkitan bentrok (409).
        """
        ...

    def update_langkah(
        self, langkah_id: str, data: LangkahUpdate, *, pelaku_kode_orang: str | None
    ) -> LangkahRead:
        """Ubah parsial langkah dan catat riwayat; `NotFoundError` bila tak ada."""
        ...
