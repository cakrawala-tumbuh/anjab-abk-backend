"""SEAM akses data kasus negatif riset. Sengaja TIDAK punya update maupun delete.

Kasus negatif bersifat append-only dan hanya bisa dicatat untuk protokol `TERKUNCI`.
Galat protokol `DRAF` memakai ulang `ProtokolBelumTerkunciError` milik statistik riset.
"""

from __future__ import annotations

from typing import Protocol

from ..schemas.riset_kasus_negatif import RisetKasusNegatifCreate, RisetKasusNegatifRead


class RisetKasusNegatifService(Protocol):
    """Kontrak penyimpanan kasus negatif riset per protokol terkunci."""

    def create(
        self, protokol_id: str, data: RisetKasusNegatifCreate, *, dibuat_oleh: str
    ) -> RisetKasusNegatifRead:
        """Simpan kasus negatif baru untuk protokol `TERKUNCI`.

        Raises:
            NotFoundError: Protokol tak ada (404).
            ProtokolBelumTerkunciError: Protokol masih `DRAF` (409 `PROTOKOL_BELUM_TERKUNCI`).
        """
        ...

    def list_by_protokol(
        self, protokol_id: str, *, limit: int, offset: int
    ) -> tuple[list[RisetKasusNegatifRead], int]:
        """Daftar kasus negatif satu protokol, urut `created_at` naik (terlama dulu).

        Raises:
            NotFoundError: Protokol tak ada (404).
        """
        ...
