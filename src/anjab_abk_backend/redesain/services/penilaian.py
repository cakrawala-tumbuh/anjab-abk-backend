"""SEAM akses data penilaian redesain (sheet PENILAIAN)."""

from __future__ import annotations

from typing import Protocol

from ...schemas.search import Domain, Order
from ..schemas.penilaian import (
    PenilaianCreate,
    PenilaianPutuskan,
    PenilaianRead,
    PenilaianStatus,
    PenilaianUpdate,
    SebaranK,
)

SEARCHABLE_FIELDS = frozenset(
    {"masalah_id", "status_bukti", "saran_otomatis", "status_penilaian", "prioritas_final"}
)
"""Field yang boleh dipakai pada domain search penilaian."""


class PenilaianService(Protocol):
    """Kontrak penilaian redesain. Sengaja TIDAK punya `delete`.

    Setiap create/update menghitung ulang `saran_otomatis` lewat `redesain.triase.hitung_saran`
    dan menyimpan `versi_aturan_triase`; keduanya tidak pernah diambil dari payload.
    """

    def create(self, data: PenilaianCreate, *, pelaku_kode_orang: str | None) -> PenilaianRead:
        """Buat penilaian untuk satu masalah dan catat riwayat.

        Raises:
            ValidationAppError: masalah tak dikenal (422).
            ConflictError: masalah sudah punya penilaian (409).
        """
        ...

    def get(self, penilaian_id: str) -> PenilaianRead:
        """Ambil satu penilaian; `NotFoundError` bila tak ada."""
        ...

    def list(self, *, limit: int, offset: int) -> tuple[list[PenilaianRead], int]:
        """Daftar berurutan menurut `created_at`."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[PenilaianRead], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`)."""
        ...

    def update(
        self, penilaian_id: str, data: PenilaianUpdate, *, pelaku_kode_orang: str | None
    ) -> PenilaianRead:
        """Ubah parsial, hitung ulang saran, dan catat riwayat."""
        ...

    def putuskan(
        self, penilaian_id: str, data: PenilaianPutuskan, *, pelaku_kode_orang: str | None
    ) -> PenilaianRead:
        """Catat keputusan prioritas final (boleh diulang), set status `Telah diputuskan`.

        Menyimpan `saran_saat_keputusan` dan mencatat riwayat `aksi="putuskan"`.

        Raises:
            NotFoundError: penilaian tak ada (404).
            ValidationAppError: kode orang pemutus tak dikenal (422).
        """
        ...

    def set_status(
        self, penilaian_id: str, data: PenilaianStatus, *, pelaku_kode_orang: str | None
    ) -> PenilaianRead:
        """Ubah status penilaian (bukan `Telah diputuskan`) dan catat riwayat `aksi="status"`."""
        ...

    def agenda_yayasan(self, *, limit: int, offset: int) -> tuple[list[PenilaianRead], int]:
        """Penilaian berstatus `Siap untuk telaah yayasan`, berurutan `created_at`."""
        ...

    def sebaran_k(self, masalah_id: str) -> SebaranK:
        """Sebaran K1–K4 konfirmasi `terkirim` tak digantikan; 404 bila masalah tak ada."""
        ...
