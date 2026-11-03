"""Operasi admin bulk lintas-tabel atas katalog master Task Inventory (purge).

Beroperasi langsung di atas `Session` (bukan lewat Protocol CRUD single-record
`TugasPokokService`/dst.) karena purge adalah operasi bulk lintas-tabel — meniru
persis `scripts/purge_task_catalog.py`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

from ...errors import CatalogInUseError
from ...models import TiDetilTugasModel, TiTugasPokokModel, TiUraianTugasModel

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ...opm.services.sesi import OpmSesiService
    from .sesi import TiSesiService


class PurgeSummary(TypedDict):
    """Ringkasan jumlah baris yang dihapus per tabel katalog."""

    uraian_tugas: int
    detil_tugas: int
    tugas_pokok: int


def guard_no_active_sesi(sesi_svc: TiSesiService, opm_sesi_svc: OpmSesiService) -> None:
    """Hard block: `CatalogInUseError` (409 `catalog_in_use`) bila katalog masih dipakai.

    Katalog dianggap dipakai bila ada >= 1 sesi Task Inventory ATAU >= 1 sesi OPM
    (status apa pun): `ti_seleksi`/`ti_tahap2`/`ti_detail` merujuk katalog lewat
    `task_kode`, dan sesi OPM menyimpan snapshot task dari katalog.

    Args:
        sesi_svc: Service sesi Task Inventory (hanya dibaca jumlahnya).
        opm_sesi_svc: Service sesi OPM (hanya dibaca jumlahnya).

    Raises:
        CatalogInUseError: Bila ada sesi TI atau OPM; pesan menyebut kedua jumlah.
    """
    _, n_ti = sesi_svc.search(domain=[], order=[], limit=1, offset=0)
    _, n_opm = opm_sesi_svc.search(domain=[], order=[], limit=1, offset=0)
    if n_ti > 0 or n_opm > 0:
        raise CatalogInUseError(
            f"Tidak dapat purge katalog: masih dipakai {n_ti} sesi Task Inventory "
            f"dan {n_opm} sesi OPM. Hapus seluruh sesi (status apa pun) sebelum purge."
        )


def purge_catalog(session: Session) -> PurgeSummary:
    """Hapus SELURUH baris `ti_uraian_tugas`, `ti_tugas_pokok`, `ti_detil_tugas`.

    Baris link M2M (`ti_tugas_pokok_jabatan`/`ti_detil_tugas_jabatan`) ikut terhapus
    otomatis lewat `ON DELETE CASCADE`. Tabel `jabatan` TIDAK disentuh. Pemanggil
    WAJIB memanggil `guard_no_active_sesi()` dulu.
    """
    n_ut = session.query(TiUraianTugasModel).delete()
    n_tp = session.query(TiTugasPokokModel).delete()
    n_dt = session.query(TiDetilTugasModel).delete()
    return PurgeSummary(uraian_tugas=n_ut, tugas_pokok=n_tp, detil_tugas=n_dt)
