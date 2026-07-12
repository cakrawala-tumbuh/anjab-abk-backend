"""Data master catalog Task Inventory.

Sumber: sheet `05_Raw_Task_Migration` dari Task_Bank_Complete_AllRoles_v2_19.xlsx,
diekstrak lewat `data/task-inventory/extract_task_bank.py` (di repo induk) lalu disimpan
sebagai `data/task_catalog.json`. Data di-load sekali saat startup (read-only, tidak
diubah lewat API). Termasuk 5 nilai standar CalHR (`std_*`) per task.

Fungsi `seed_catalog_models` memigrasikan data JSON ke tiga model terpisah:
TugasPokok, DetilTugas, dan UraianTugas — yang menjadi sumber tunggal data catalog.

Jabatan di-auto-create dari string `kategori_jabatan` pada catalog JSON bila belum ada.
TugasPokok memiliki M2M ke Jabatan (jabatan_ids). DetilTugas juga M2M ke Jabatan
(jabatan_ids, subset dari parent TugasPokok). UraianTugas memiliki M2O ke Jabatan
(jabatan_id, langsung tersimpan).
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from ..anjab.services.jabatan import JabatanService
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
    std_va_type: str | None
    std_sumber_bukti: str | None
    std_kondisi: str | None
    std_frekuensi_teks: str | None
    std_durasi_per_kali: str | None


@lru_cache
def load_catalog() -> list[CatalogItem]:
    """Muat catalog task dari berkas JSON (di-cache setelah pemanggilan pertama)."""
    with _DATA_FILE.open(encoding="utf-8") as f:
        data: list[CatalogItem] = json.load(f)
    return data


def _slug_kode(nama: str) -> str:
    """Buat kode jabatan dari nama (uppercase + underscore, maks 28 karakter)."""
    slug = re.sub(r"[^a-z0-9]+", "_", nama.lower()).strip("_")[:28]
    return f"CAT_{slug[:24]}" if slug else "CAT_jabatan"


def seed_catalog_models(
    tp_svc: TugasPokokService,
    dt_svc: DetilTugasService,
    ut_svc: UraianTugasService,
    jabatan_svc: JabatanService,
) -> None:
    """Seed Jabatan, TugasPokok, DetilTugas, UraianTugas dari task_catalog.json.

    Fungsi ini idempoten: data yang sudah ada (duplikat) di-skip tanpa error.
    Dipanggil satu kali saat startup oleh factory di dependencies.py.
    Saat PostgreSQL terhubung, fungsi ini dapat diganti Alembic data migration.

    Alur:
    1. Auto-create Jabatan dari string `kategori_jabatan` (bila belum ada).
    2. Akumulasi jabatan_ids per nama TugasPokok, lalu seed TugasPokok (unik by nama).
    3. Akumulasi jabatan_ids per (tp_id, dt_nama), lalu seed DetilTugas.
    4. Seed UraianTugas dengan jabatan_id eksplisit (M2O langsung).
    """
    from ..anjab.schemas.jabatan import JabatanCreate
    from ..errors import ConflictError
    from .schemas.detil_tugas import DetilTugasCreate
    from .schemas.tugas_pokok import TugasPokokCreate, TugasPokokUpdate
    from .schemas.uraian_tugas import UraianTugasCreate

    catalog = load_catalog()

    # Langkah 1: auto-create Jabatan dari string kategori_jabatan
    jabatan_id_by_nama: dict[str, str] = {}
    seen_jbt: set[str] = set()
    for item in catalog:
        nama = item["kategori_jabatan"]
        if nama in seen_jbt:
            continue
        seen_jbt.add(nama)
        rows, _ = jabatan_svc.search(domain=[["nama", "=", nama]], order=[], limit=1, offset=0)
        if rows:
            jabatan_id_by_nama[nama] = rows[0].id
        else:
            kode = _slug_kode(nama)
            suffix = 0
            kode_try = kode
            while True:
                existing, _ = jabatan_svc.search(
                    domain=[["kode", "=", kode_try]], order=[], limit=1, offset=0
                )
                if not existing:
                    break
                suffix += 1
                kode_try = f"{kode[:25]}_{suffix}"
            try:
                r = jabatan_svc.create(
                    JabatanCreate(
                        kode=kode_try,
                        nama=nama,
                        jenis="fungsional",
                        aktif=True,
                    )
                )
                jabatan_id_by_nama[nama] = r.id
            except ConflictError:
                rows2, _ = jabatan_svc.search(
                    domain=[["nama", "=", nama]], order=[], limit=1, offset=0
                )
                if rows2:
                    jabatan_id_by_nama[nama] = rows2[0].id

    # Langkah 2: akumulasi jabatan_ids per nama TugasPokok, lalu seed
    tp_jabatan_ids: dict[str, list[str]] = {}  # nama → [jabatan_id, ...]
    for item in catalog:
        jabatan_id = jabatan_id_by_nama.get(item["kategori_jabatan"], "")
        nama = item["tugas_pokok"]
        if nama not in tp_jabatan_ids:
            tp_jabatan_ids[nama] = []
        if jabatan_id and jabatan_id not in tp_jabatan_ids[nama]:
            tp_jabatan_ids[nama].append(jabatan_id)

    tp_by_nama: dict[str, str] = {}  # nama → tp_id
    for nama, jabatan_ids in tp_jabatan_ids.items():
        if not jabatan_ids:
            continue
        rows, _ = tp_svc.search(domain=[["nama", "=", nama]], order=[], limit=1, offset=0)
        if rows:
            tp_by_nama[nama] = rows[0].id
            # Tambahkan jabatan_ids baru yang belum ada
            current_ids = set(rows[0].jabatan_ids)
            new_ids = set(jabatan_ids)
            if not new_ids.issubset(current_ids):
                tp_svc.update(rows[0].id, TugasPokokUpdate(jabatan_ids=list(current_ids | new_ids)))
        else:
            try:
                r = tp_svc.create(TugasPokokCreate(jabatan_ids=jabatan_ids, nama=nama))
                tp_by_nama[nama] = r.id
            except ConflictError:
                rows2, _ = tp_svc.search(domain=[["nama", "=", nama]], order=[], limit=1, offset=0)
                if rows2:
                    tp_by_nama[nama] = rows2[0].id

    # Langkah 3: akumulasi jabatan_ids per (tp_id, dt_nama), lalu seed DetilTugas
    dt_jabatan_ids: dict[tuple[str, str], list[str]] = {}  # (tp_id, dt_nama) → [jabatan_id, ...]
    for item in catalog:
        dt_nama = item["detil_tugas"].strip()
        if not dt_nama:
            continue
        jabatan_id = jabatan_id_by_nama.get(item["kategori_jabatan"], "")
        tp_id = tp_by_nama.get(item["tugas_pokok"], "")
        if not tp_id:
            continue
        key = (tp_id, dt_nama)
        if key not in dt_jabatan_ids:
            dt_jabatan_ids[key] = []
        if jabatan_id and jabatan_id not in dt_jabatan_ids[key]:
            dt_jabatan_ids[key].append(jabatan_id)

    dt_by_key: dict[tuple[str, str], str] = {}  # (tp_id, dt_nama) → dt_id
    for (tp_id, dt_nama), jabatan_ids in dt_jabatan_ids.items():
        if not jabatan_ids:
            continue
        rows, _ = dt_svc.search(
            domain=[["nama", "=", dt_nama], ["tugas_pokok_id", "=", tp_id]],
            order=[],
            limit=1,
            offset=0,
        )
        if rows:
            dt_by_key[(tp_id, dt_nama)] = rows[0].id
            current_ids = set(rows[0].jabatan_ids)
            new_ids = set(jabatan_ids)
            if not new_ids.issubset(current_ids):
                from .schemas.detil_tugas import DetilTugasUpdate

                dt_svc.update(
                    rows[0].id,
                    DetilTugasUpdate(jabatan_ids=list(current_ids | new_ids)),
                )
        else:
            try:
                r = dt_svc.create(
                    DetilTugasCreate(nama=dt_nama, tugas_pokok_id=tp_id, jabatan_ids=jabatan_ids)
                )
                dt_by_key[(tp_id, dt_nama)] = r.id
            except ConflictError:
                rows2, _ = dt_svc.search(
                    domain=[["nama", "=", dt_nama], ["tugas_pokok_id", "=", tp_id]],
                    order=[],
                    limit=1,
                    offset=0,
                )
                if rows2:
                    dt_by_key[(tp_id, dt_nama)] = rows2[0].id

    # Langkah 4: seed UraianTugas dengan jabatan_id eksplisit
    for item in catalog:
        jabatan_id = jabatan_id_by_nama.get(item["kategori_jabatan"], "")
        tp_id = tp_by_nama.get(item["tugas_pokok"], "")
        dt_nama = item["detil_tugas"].strip()
        dt_id = dt_by_key.get((tp_id, dt_nama)) if dt_nama else None
        if not jabatan_id or not tp_id:
            continue
        try:
            ut_svc.create(
                UraianTugasCreate(
                    kode=item["kode"],
                    uraian=item["uraian_tugas"],
                    unit=item["unit"],
                    urutan=item["urutan"],
                    jabatan_id=jabatan_id,
                    detil_tugas_id=dt_id or None,
                    tugas_pokok_id=tp_id,
                    std_va_type=item.get("std_va_type"),
                    std_sumber_bukti=item.get("std_sumber_bukti"),
                    std_kondisi=item.get("std_kondisi"),
                    std_frekuensi_teks=item.get("std_frekuensi_teks"),
                    std_durasi_per_kali=item.get("std_durasi_per_kali"),
                )
            )
        except ConflictError:
            pass  # kode sudah ada, skip

    _logger.info(
        "seed_catalog_models: %d jabatan, %d TP, %d DT, %d UT di-seed dari task_catalog.json",
        len(jabatan_id_by_nama),
        len(tp_by_nama),
        len(dt_by_key),
        len(catalog),
    )
