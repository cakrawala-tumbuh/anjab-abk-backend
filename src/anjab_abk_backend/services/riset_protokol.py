"""SEAM akses data protokol riset. Sengaja TIDAK punya update/delete umum.

Satu-satunya perubahan baris yang sah adalah `kunci()` (DRAF -> TERKUNCI), sekali saja.
"""

from __future__ import annotations

from typing import Protocol

from ..errors import ConflictError
from ..schemas.riset_protokol import RisetProtokolCreate, RisetProtokolRead, RisetProtokolRingkas


class ProtokolTerkunciError(ConflictError):
    """409: protokol sudah `TERKUNCI`, sehingga tidak dapat dikunci (atau diubah) lagi."""

    error_code = "PROTOKOL_TERKUNCI"


class RisetProtokolService(Protocol):
    """Kontrak penyimpanan protokol riset berversi."""

    def create(self, data: RisetProtokolCreate, *, dibuat_oleh: str) -> RisetProtokolRead:
        """Simpan protokol `DRAF` baru; `versi` = versi terbesar `kode` itu + 1 (mulai 1).

        Raises:
            ConflictError: Pasangan (`kode`, `versi`) bentrok dengan permintaan bersamaan (409).
        """
        ...

    def get(self, protokol_id: str) -> RisetProtokolRead:
        """Ambil satu protokol lengkap; `NotFoundError` (404) bila tak ada."""
        ...

    def list(
        self, *, kode: str | None, status: str | None, limit: int, offset: int
    ) -> tuple[list[RisetProtokolRingkas], int]:
        """Daftar ringkas (tanpa `isi`), terbaru dulu, dengan filter opsional."""
        ...

    def kunci(self, protokol_id: str, *, dikunci_oleh: str) -> RisetProtokolRead:
        """Kunci protokol permanen: status `TERKUNCI`, `isi_hash` SHA-256, aktor, dan waktu.

        Raises:
            NotFoundError: Protokol tak ada (404).
            ProtokolTerkunciError: Protokol sudah terkunci (409 `PROTOKOL_TERKUNCI`).
        """
        ...
