"""SEAM baca ringkasan yayasan (sheet YAYASAN): read-model dari masalah + penilaian."""

from __future__ import annotations

from typing import Protocol

from ...schemas.search import Domain, Order
from ..schemas.yayasan import RingkasanYayasanRow

SEARCHABLE_FIELDS = frozenset(
    {"konteks_kode", "status_bukti", "saran_otomatis", "prioritas_final", "status_penilaian"}
)
"""Field yang boleh dipakai pada domain search ringkasan yayasan."""


class RingkasanYayasanService(Protocol):
    """Kontrak baca ringkasan yayasan; hanya READ + search, tanpa tulis."""

    def list(self, *, limit: int, offset: int) -> tuple[list[RingkasanYayasanRow], int]:
        """Daftar baris berurutan menurut kode masalah."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[RingkasanYayasanRow], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`)."""
        ...

    def get(self, masalah_id: str) -> RingkasanYayasanRow:
        """Ambil satu baris per masalah; `NotFoundError` (404) bila masalah tak ada."""
        ...
