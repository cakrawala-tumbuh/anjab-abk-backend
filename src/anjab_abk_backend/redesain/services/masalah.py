"""SEAM akses data masalah redesain (sheet MASALAH)."""

from __future__ import annotations

from typing import Protocol

from ...schemas.search import Domain, Order
from ..schemas.masalah import MasalahCreate, MasalahRead, MasalahUpdate

SEARCHABLE_FIELDS = frozenset(
    {
        "id",
        "kode",
        "konteks_id",
        "sekolah_id",
        "status_awal",
        "gelombang",
        "dibuka_untuk_konfirmasi",
        "eskalasi_pada",
    }
)
"""Field yang boleh dipakai pada domain/order search masalah (termasuk `id` untuk lookup massal)."""


class MasalahService(Protocol):
    """Kontrak masalah redesain. Sengaja TIDAK punya `delete`."""

    def create(
        self,
        data: MasalahCreate,
        *,
        pelaku_kode_orang: str | None,
        sumber_konfirmasi_id: str | None = None,
    ) -> MasalahRead:
        """Buat masalah (kode dibangkitkan) beserta tautan uraian tugas, lalu catat riwayat.

        `sumber_konfirmasi_id` diisi hanya oleh alur angkat-masalah dari konfirmasi.

        Raises:
            ValidationAppError: konteks/sekolah/uraian tugas tidak dikenal (422).
            ConflictError: kode hasil bangkitan bentrok (409).
        """
        ...

    def get(self, masalah_id: str) -> MasalahRead:
        """Ambil satu masalah; `NotFoundError` bila tak ada."""
        ...

    def list(self, *, limit: int, offset: int) -> tuple[list[MasalahRead], int]:
        """Daftar berurutan menurut `kode`."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[MasalahRead], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`)."""
        ...

    def update(
        self, masalah_id: str, data: MasalahUpdate, *, pelaku_kode_orang: str | None
    ) -> MasalahRead:
        """Ubah parsial; `ConflictError` bila `status_awal` diubah saat sudah dibekukan."""
        ...

    def set_status_konfirmasi(
        self, masalah_id: str, dibuka: bool, *, pelaku_kode_orang: str | None
    ) -> MasalahRead:
        """Buka/tutup masalah untuk konfirmasi sekolah dan catat riwayat."""
        ...
