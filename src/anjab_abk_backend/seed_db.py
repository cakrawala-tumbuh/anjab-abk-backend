"""Seed master/reference data ke PostgreSQL (idempoten).

Mengisi data referensi yang sebelumnya di-seed otomatis oleh placeholder in-memory:
- DCS: 3 sub-skala + 42 item (`dcs/seed.py`)
- WCP: 12 dimensi + 72 item (`wcp/seed.py`)
- Task Inventory: Jabatan + TugasPokok + DetilTugas + UraianTugas dari
  `taskinv/data/task_catalog.json` (`taskinv/seed.py::seed_catalog_models`)

Jalankan sebagai langkah deploy SETELAH `alembic upgrade head`:

    python -m anjab_abk_backend.seed_db

Idempoten: dijalankan berkali-kali aman — baris yang sudah ada di-skip. BUKAN
dijalankan otomatis saat startup (hindari balapan antar-replika & jaga
`create_app()` bebas efek samping).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import session_scope
from .dcs.seed import ITEM as DCS_ITEM
from .dcs.seed import SUB_SKALA as DCS_SUB_SKALA
from .models import DcsItemModel, DcsSubSkalaModel, WcpDimensiModel, WcpItemModel
from .wcp.seed import DIMENSI as WCP_DIMENSI
from .wcp.seed import ITEM as WCP_ITEM

logger = logging.getLogger("anjab_abk_backend.seed")


def _seed_dcs(session: Session) -> None:
    existing_sk = set(session.scalars(select(DcsSubSkalaModel.kode)).all())
    for kode, nama, urutan in DCS_SUB_SKALA:
        if kode in existing_sk:
            continue
        session.add(DcsSubSkalaModel(id=f"dsk_{kode}", kode=kode, nama=nama, urutan=urutan))

    existing_item = set(session.scalars(select(DcsItemModel.item_id)).all())
    for item_id, subskala_kode, sub_dimensi, pernyataan, arah, urutan in DCS_ITEM:
        if item_id in existing_item:
            continue
        session.add(
            DcsItemModel(
                id=f"ditm_{item_id}",
                item_id=item_id,
                subskala_kode=subskala_kode,
                sub_dimensi=sub_dimensi,
                pernyataan=pernyataan,
                arah=arah,
                urutan=urutan,
            )
        )
    session.flush()


def _seed_wcp(session: Session) -> None:
    existing_dim = set(session.scalars(select(WcpDimensiModel.kode)).all())
    for kode, nama, urutan, is_risk in WCP_DIMENSI:
        if kode in existing_dim:
            continue
        session.add(
            WcpDimensiModel(id=f"wdim_{kode}", kode=kode, nama=nama, urutan=urutan, is_risk=is_risk)
        )

    existing_item = set(session.scalars(select(WcpItemModel.item_id)).all())
    for item_id, kode_dim, ind_kode, ind_label, pernyataan, rev_type, urutan in WCP_ITEM:
        if item_id in existing_item:
            continue
        session.add(
            WcpItemModel(
                id=f"witm_{item_id}",
                item_id=item_id,
                dimensi_kode=kode_dim,
                indikator_kode=ind_kode,
                indikator_label=ind_label,
                pernyataan=pernyataan,
                reverse_type=rev_type,
                urutan=urutan,
            )
        )
    session.flush()


def _seed_taskinv(session: Session) -> None:
    # seed_catalog_models bekerja lewat Protocol service (idempoten via ConflictError),
    # jadi cukup beri implementasi PostgreSQL yang terikat sesi ini.
    from .anjab.services.jabatan_sql import SqlJabatanService
    from .taskinv.seed import seed_catalog_models
    from .taskinv.services.detil_tugas_sql import SqlDetilTugasService
    from .taskinv.services.tugas_pokok_sql import SqlTugasPokokService
    from .taskinv.services.uraian_tugas_sql import SqlUraianTugasService

    seed_catalog_models(
        SqlTugasPokokService(session),
        SqlDetilTugasService(session),
        SqlUraianTugasService(session),
        SqlJabatanService(session),
    )


def seed_all(session: Session) -> None:
    """Seed seluruh master data (DCS, WCP, Task Inventory) dalam satu transaksi."""
    _seed_dcs(session)
    _seed_wcp(session)
    _seed_taskinv(session)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    with session_scope() as session:
        seed_all(session)
    logger.info("seed master data selesai")


if __name__ == "__main__":
    main()
