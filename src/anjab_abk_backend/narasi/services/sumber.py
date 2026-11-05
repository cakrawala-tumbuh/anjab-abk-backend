"""SEAM akses data sumber narasi. Sengaja TIDAK punya update/delete (baris tak berubah)."""

from __future__ import annotations

from typing import Protocol

from ...schemas.search import Domain, Order
from ..schemas.sumber import NarasiSumberCreate, NarasiSumberRead, NarasiSumberRingkas

SEARCHABLE_FIELDS = frozenset({"jenis", "periode", "judul", "izin_ai", "created_at"})
"""Field yang boleh dipakai pada domain search sumber narasi."""


class NarasiSumberService(Protocol):
    """Kontrak penyimpanan sumber narasi yang tak dapat diubah."""

    def create(self, data: NarasiSumberCreate, *, dibuat_oleh: str) -> NarasiSumberRead:
        """Simpan sumber baru dengan `teks_hash` SHA-256.

        Raises:
            ValidationAppError: `menggantikan_id` tak dikenal (422).
        """
        ...

    def get(self, sumber_id: str) -> NarasiSumberRead:
        """Ambil satu sumber; `NotFoundError` bila tak ada."""
        ...

    def list(
        self, *, jenis: str | None, periode: str | None, limit: int, offset: int
    ) -> tuple[list[NarasiSumberRingkas], int]:
        """Daftar ringkas (tanpa teks), terbaru dulu, dengan filter opsional."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[NarasiSumberRingkas], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`)."""
        ...
