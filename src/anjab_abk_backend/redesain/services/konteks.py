"""SEAM akses data katalog konteks redesain."""

from __future__ import annotations

from typing import Protocol

from ...schemas.search import Domain, Order
from ..schemas.konteks import KonteksCreate, KonteksRead, KonteksUpdate

SEARCHABLE_FIELDS = frozenset(
    {"id", "kode", "tema", "gelombang", "aktif", "created_at", "updated_at"}
)


class KonteksService(Protocol):
    """Kontrak katalog konteks. Sengaja TIDAK punya `delete` (gunakan `aktif=false`)."""

    def create(self, data: KonteksCreate, *, pelaku_kode_orang: str | None) -> KonteksRead:
        """Buat konteks dan catat riwayat; `ConflictError` bila `kode` duplikat."""
        ...

    def get(self, konteks_id: str) -> KonteksRead:
        """Ambil satu konteks; `NotFoundError` bila tak ada."""
        ...

    def list(self, *, limit: int, offset: int) -> tuple[list[KonteksRead], int]:
        """Daftar berurutan menurut `kode`."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[KonteksRead], int]:
        """Cari memakai domain ala Odoo."""
        ...

    def update(
        self, konteks_id: str, data: KonteksUpdate, *, pelaku_kode_orang: str | None
    ) -> KonteksRead:
        """Ubah parsial dan catat riwayat."""
        ...
