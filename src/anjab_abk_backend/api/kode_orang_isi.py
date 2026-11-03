"""Helper pengisi `kode_orang` pada respons responden TI/OPM/WCP/DCS.

Domain TI/OPM/WCP/DCS tidak meng-query tabel redesain; kode orang diresolusi di
lapisan router lewat `KodeOrangService` (komposisi), sehingga skema `*RespondenRead`
memuat pseudonim alih-alih nama.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from ..redesain.services.kode_orang import KodeOrangService


class _BerKodeOrang(Protocol):
    """Objek respons responden yang punya `partisipan_id` dan `kode_orang`."""

    partisipan_id: str | None
    kode_orang: str | None


def isi_kode_orang(
    items: Iterable[_BerKodeOrang], ko_service: KodeOrangService, *, jamin: bool = False
) -> None:
    """Isi `kode_orang` tiap item secara massal (in-place).

    Args:
        items: Objek `*RespondenRead` yang akan diisi.
        ko_service: Seam kode orang.
        jamin: Bila True, buat dulu kode (idempoten, `untuk_partisipan`) untuk setiap
            partisipan yang belum punya — dipakai jalur penugasan/penambahan responden.
            Jalur GET memakai False sehingga tidak ada efek tulis.

    Note:
        Item tanpa `partisipan_id` mendapat `kode_orang=None`.
    """
    daftar = list(items)
    ids = list(dict.fromkeys(i.partisipan_id for i in daftar if i.partisipan_id))
    if jamin:
        for pid in ids:
            ko_service.untuk_partisipan(pid)
    peta = ko_service.peta_partisipan(ids)
    for i in daftar:
        i.kode_orang = peta.get(i.partisipan_id) if i.partisipan_id else None
