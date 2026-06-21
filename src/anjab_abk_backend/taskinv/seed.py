"""Data master catalog Task Inventory.

Sumber: `Rekap Data FGD dan Analisis Beban Kerja.csv` (hasil FGD YPII), di-dedup per
identitas (Unit, Kategori Jabatan, Tugas Pokok, Detil Tugas, Uraian Tugas) lalu disimpan
sebagai `data/task_catalog.json`. Data di-load sekali saat startup (read-only, tidak
diubah lewat API). Lihat sheet `02_Task_Inventory` (standar CalHR 5-komponen).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import TypedDict

_DATA_FILE = Path(__file__).parent / "data" / "task_catalog.json"


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
