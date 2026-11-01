"""SEAM akses data cakupan jabatan redesain (sheet CAKUPAN_19)."""

from __future__ import annotations

from typing import Protocol

from ...schemas.search import Domain, Order
from ..schemas.cakupan_jabatan import (
    CakupanJabatanCreate,
    CakupanJabatanRead,
    CakupanJabatanUpdate,
)

SEARCHABLE_FIELDS = frozenset({"id", "role_kode", "cabang", "status_unit", "jabatan_id"})
"""Field yang boleh dipakai pada domain search cakupan jabatan."""


class CakupanJabatanService(Protocol):
    """Kontrak cakupan jabatan. Sengaja TIDAK punya `delete`."""

    def create(
        self, data: CakupanJabatanCreate, *, pelaku_kode_orang: str | None
    ) -> CakupanJabatanRead:
        """Buat entri dan catat riwayat.

        Raises:
            ValidationAppError: jabatan/kode orang tak dikenal (422).
            ConflictError: pasangan `role_kode`+`cabang` sudah ada (409).
        """
        ...

    def get(self, cakupan_id: str) -> CakupanJabatanRead:
        """Ambil satu entri; `NotFoundError` bila tak ada."""
        ...

    def list(self, *, limit: int, offset: int) -> tuple[list[CakupanJabatanRead], int]:
        """Daftar berurutan menurut `role_kode` lalu `cabang`."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[CakupanJabatanRead], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`)."""
        ...

    def update(
        self, cakupan_id: str, data: CakupanJabatanUpdate, *, pelaku_kode_orang: str | None
    ) -> CakupanJabatanRead:
        """Ubah parsial dan catat riwayat."""
        ...
