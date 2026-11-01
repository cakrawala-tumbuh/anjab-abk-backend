"""SEAM akses data konfirmasi sekolah redesain (sheet KONFIRMASI).

Kontrak ini menegakkan urutan anti-persetujuan-semu: cerita dikunci → dugaan
ditampilkan → penilaian → kirim. Tidak ada operasi hapus maupun ganti penuh.
"""

from __future__ import annotations

from typing import Protocol

from ...schemas.search import Domain, Order
from ..schemas.konfirmasi import (
    AngkatMasalahCreate,
    DugaanRead,
    KonfirmasiDaftarRead,
    KonfirmasiLuringCreate,
    KonfirmasiRead,
    KonfirmasiUpdate,
    MasalahSekolahRead,
)
from ..schemas.masalah import MasalahRead

SEARCHABLE_FIELDS = frozenset(
    {"masalah_id", "sekolah_id", "kode_orang", "status", "sumber", "indikasi_risiko"}
)
"""Field yang boleh dipakai pada domain search konfirmasi (khusus `tim-kajian`)."""


class KonfirmasiService(Protocol):
    """Kontrak konfirmasi sekolah. Semua aksi tulis hanya untuk draf milik `kode_orang`."""

    def list_masalah_sekolah(
        self, sekolah_id: str, *, limit: int, offset: int
    ) -> tuple[list[MasalahSekolahRead], int]:
        """Masalah `dibuka_untuk_konfirmasi` milik `sekolah_id` (tanpa rumusan hipotesis)."""
        ...

    def create(self, masalah_id: str, *, kode_orang: str, sekolah_id: str) -> KonfirmasiRead:
        """Buat draf untuk (masalah, kode_orang).

        Raises:
            NotFoundError: masalah tak ada (404).
            ForbiddenError: masalah bukan milik `sekolah_id` atau belum dibuka (403).
            ConflictError: sudah ada draf/terkirim untuk pasangan yang sama (409).
        """
        ...

    def get(self, konfirmasi_id: str) -> KonfirmasiRead:
        """Ambil satu konfirmasi; `NotFoundError` bila tak ada."""
        ...

    def update(
        self, konfirmasi_id: str, data: KonfirmasiUpdate, *, kode_orang: str
    ) -> KonfirmasiRead:
        """Ubah parsial draf milik sendiri dengan gerbang urutan (lihat implementasi)."""
        ...

    def kunci_cerita(self, konfirmasi_id: str, *, kode_orang: str) -> KonfirmasiRead:
        """Kunci `cerita_sebelum` (422 bila kosong/spasi); idempoten bila sudah terkunci."""
        ...

    def tampilkan_dugaan(self, konfirmasi_id: str, *, kode_orang: str) -> DugaanRead:
        """Tampilkan rumusan hipotesis; 409 `CERITA_BELUM_DIKUNCI` bila cerita belum dikunci."""
        ...

    def kirim(self, konfirmasi_id: str, *, kode_orang: str) -> KonfirmasiRead:
        """Kirim draf (422 bila field wajib kosong); membekukan status awal & menandai eskalasi."""
        ...

    def ralat(self, konfirmasi_id: str, *, kode_orang: str) -> KonfirmasiRead:
        """Buat draf ralat (versi baru) dari konfirmasi terkirim milik sendiri.

        Raises:
            ForbiddenError: konfirmasi milik orang lain (403).
            KonfirmasiConflictError: masih draf, sudah digantikan, atau sudah ada draf (409).
        """
        ...

    def list_saya(
        self, kode_orang: str, *, limit: int, offset: int
    ) -> tuple[list[KonfirmasiDaftarRead], int]:
        """Seluruh versi konfirmasi milik `kode_orang`, terlama dulu."""
        ...

    def list_semua(self, *, limit: int, offset: int) -> tuple[list[KonfirmasiDaftarRead], int]:
        """Seluruh konfirmasi (untuk Tim), terlama dulu."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[KonfirmasiDaftarRead], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`)."""
        ...

    def angkat_masalah(
        self, konfirmasi_id: str, data: AngkatMasalahCreate, *, pelaku_kode_orang: str | None
    ) -> MasalahRead:
        """Angkat `masalah_baru` konfirmasi terkirim menjadi masalah `Keterangan kasus`."""
        ...

    def luring(
        self, data: KonfirmasiLuringCreate, *, pelaku_kode_orang: str | None
    ) -> KonfirmasiRead:
        """Simpan isian kertas atas nama pemberi keterangan, langsung `terkirim`."""
        ...
