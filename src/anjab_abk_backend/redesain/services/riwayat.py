"""SEAM akses data riwayat perubahan redesain (append-only: tanpa update/delete)."""

from __future__ import annotations

from typing import Any, Protocol

from ...schemas.search import Domain, Order
from ..schemas.riwayat import RiwayatRead

SEARCHABLE_FIELDS = frozenset({"id", "entitas", "entitas_id", "aksi", "pelaku_kode_orang", "waktu"})


class RiwayatService(Protocol):
    """Kontrak buku riwayat. Sengaja TIDAK punya operasi ubah/hapus."""

    def catat(
        self,
        entitas: str,
        entitas_id: str,
        aksi: str,
        sebelum: dict[str, Any] | None,
        sesudah: dict[str, Any] | None,
        pelaku_kode_orang: str | None,
    ) -> RiwayatRead:
        """Tambahkan satu catatan di sesi/transaksi yang sama dengan perubahan entitas."""
        ...

    def list(
        self,
        *,
        entitas: str | None,
        entitas_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[RiwayatRead], int]:
        """Daftar riwayat (terbaru dulu), opsional disaring entitas/entitas_id."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[RiwayatRead], int]:
        """Cari riwayat memakai domain ala Odoo."""
        ...
