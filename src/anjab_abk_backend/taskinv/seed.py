"""Data master catalog Task Inventory.

Sumber: `Rekap Data FGD dan Analisis Beban Kerja.csv` (hasil FGD YPII), di-dedup per
identitas (Unit, Kategori Jabatan, Tugas Pokok, Detil Tugas, Uraian Tugas) lalu disimpan
sebagai `data/task_catalog.json`. Data di-load sekali saat startup (read-only, tidak
diubah lewat API). Lihat sheet `02_Task_Inventory` (standar CalHR 5-komponen).

Fungsi `seed_catalog_models` memigrasikan data JSON ke tiga model terpisah:
TugasPokok, DetilTugas, dan UraianTugas — yang menjadi sumber tunggal data catalog.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from .services.detil_tugas import DetilTugasService
    from .services.tugas_pokok import TugasPokokService
    from .services.uraian_tugas import UraianTugasService

_DATA_FILE = Path(__file__).parent / "data" / "task_catalog.json"
_logger = logging.getLogger(__name__)


class CatalogItem(TypedDict):
    """Satu item catalog task (hasil load JSON)."""

    kode: str
    unit: str
    kategori_jabatan: str
    tugas_pokok: str
    detil_tugas: str
    uraian_tugas: str
    urutan: int


@lru_cache
def load_catalog() -> list[CatalogItem]:
    """Muat catalog task dari berkas JSON (di-cache setelah pemanggilan pertama)."""
    with _DATA_FILE.open(encoding="utf-8") as f:
        data: list[CatalogItem] = json.load(f)
    return data


def seed_catalog_models(
    tp_svc: TugasPokokService,
    dt_svc: DetilTugasService,
    ut_svc: UraianTugasService,
) -> None:
    """Seed TugasPokok, DetilTugas, UraianTugas dari task_catalog.json.

    Fungsi ini idempoten: data yang sudah ada (kode duplikat) di-skip tanpa error.
    Dipanggil satu kali saat startup oleh factory di dependencies.py.
    Saat PostgreSQL terhubung, fungsi ini dapat diganti Alembic data migration.
    """
    from ..errors import ConflictError
    from .schemas.detil_tugas import DetilTugasCreate
    from .schemas.tugas_pokok import TugasPokokCreate
    from .schemas.uraian_tugas import UraianTugasCreate

    catalog = load_catalog()
    tp_by_nama: dict[str, str] = {}
    dt_by_key: dict[tuple[str, str], str] = {}

    # Langkah 1: seed TugasPokok (dedup by nama)
    seen_tp: set[str] = set()
    for item in catalog:
        nama = item["tugas_pokok"]
        if nama not in seen_tp:
            seen_tp.add(nama)
            try:
                r = tp_svc.create(TugasPokokCreate(nama=nama))
                tp_by_nama[nama] = r.id
            except ConflictError:
                # Sudah ada — cari id via search
                rows, _ = tp_svc.search(domain=[["nama", "=", nama]], order=[], limit=1, offset=0)
                if rows:
                    tp_by_nama[nama] = rows[0].id

    # Langkah 2: seed DetilTugas (dedup by nama + tugas_pokok_id; skip jika nama kosong)
    seen_dt: set[tuple[str, str]] = set()
    for item in catalog:
        dt_nama = item["detil_tugas"].strip()
        if not dt_nama:
            continue  # task tanpa detil tugas; detil_tugas_id akan None
        key = (item["tugas_pokok"], dt_nama)
        if key not in seen_dt:
            seen_dt.add(key)
            tp_id = tp_by_nama.get(item["tugas_pokok"], "")
            try:
                r = dt_svc.create(DetilTugasCreate(nama=dt_nama, tugas_pokok_id=tp_id))
                dt_by_key[key] = r.id
            except ConflictError:
                rows, _ = dt_svc.search(
                    domain=[["nama", "=", dt_nama], ["tugas_pokok_id", "=", tp_id]],
                    order=[],
                    limit=1,
                    offset=0,
                )
                if rows:
                    dt_by_key[key] = rows[0].id

    # Langkah 3: seed UraianTugas (unik by kode)
    for item in catalog:
        tp_id = tp_by_nama.get(item["tugas_pokok"], "")
        dt_nama = item["detil_tugas"].strip()
        dt_id = dt_by_key.get((item["tugas_pokok"], dt_nama)) if dt_nama else None
        try:
            ut_svc.create(
                UraianTugasCreate(
                    kode=item["kode"],
                    uraian=item["uraian_tugas"],
                    unit=item["unit"],
                    kategori_jabatan=item["kategori_jabatan"],
                    urutan=item["urutan"],
                    detil_tugas_id=dt_id or None,
                    tugas_pokok_id=tp_id,
                )
            )
        except ConflictError:
            pass  # kode sudah ada, skip

    _logger.info(
        "seed_catalog_models: %d TP, %d DT, %d UT di-seed dari task_catalog.json",
        len(tp_by_nama),
        len(dt_by_key),
        len(catalog),
    )
