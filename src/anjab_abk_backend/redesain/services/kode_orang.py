"""SEAM akses data kode orang (pseudonim) redesain."""

from __future__ import annotations

from typing import Protocol

from ...schemas.search import Domain, Order
from ..schemas.kode_orang import KodeOrangCreate, KodeOrangRead, KodeOrangUpdate

SEARCHABLE_FIELDS = frozenset({"id", "kode", "partisipan_id", "keterangan_peran", "created_at"})


class KodeOrangService(Protocol):
    """Kontrak kode orang. Sengaja TIDAK punya `delete` (kode stabil, tak didaur ulang)."""

    def untuk_partisipan(self, partisipan_id: str) -> KodeOrangRead:
        """Ambil kode partisipan; buat bila belum ada (idempoten)."""
        ...

    def peta_partisipan(self, partisipan_ids: list[str]) -> dict[str, str]:
        """Baca massal kode orang per partisipan (tanpa efek tulis)."""
        ...

    def create(self, data: KodeOrangCreate, *, pelaku_kode_orang: str | None) -> KodeOrangRead:
        """Daftarkan orang baru dan catat riwayatnya."""
        ...

    def get(self, kode_orang_id: str) -> KodeOrangRead:
        """Ambil satu baris; `NotFoundError` bila tak ada."""
        ...

    def list(self, *, limit: int, offset: int) -> tuple[list[KodeOrangRead], int]:
        """Daftar berurutan menurut `kode`."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[KodeOrangRead], int]:
        """Cari memakai domain ala Odoo."""
        ...

    def update(
        self, kode_orang_id: str, data: KodeOrangUpdate, *, pelaku_kode_orang: str | None
    ) -> KodeOrangRead:
        """Ubah `keterangan_peran` dan catat riwayatnya."""
        ...
