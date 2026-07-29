"""backfill nilai standar OPM dari v2.19 ke ti_uraian_tugas_jabatan

Revision ID: ad595b80d3d1
Revises: c8fb8be9e184
Create Date: 2026-07-29 02:45:00.000000

Backlog `anjab-abk-backend#33`. Mengisi tiga kolom yang ditambahkan revisi sebelumnya
(`c8fb8be9e184`) untuk baris `ti_uraian_tugas_jabatan` yang sudah ada di instance yang
sudah berjalan — `task_catalog.json` sudah diperbarui in-place pada commit yang sama
(memengaruhi instalasi BARU lewat `seed_catalog_models`), tetapi seeding hanya
**membuat** baris yang belum ada, tidak menyentuh baris lama.

Sumber nilai: sheet `05_Raw_Task_Migration`
(`Task_Bank_Complete_AllRoles_v2_19 (1).xlsx`), kolom `Importance` (1-5, penuh
1138/1138), `Criticality` (1-5, penuh 1138/1138), dan `Frequency` (teks, dipetakan ke
skor 1-5: Insidental=1, Tahunan=2, Semesteran=2, Bulanan=3, Mingguan=4, Harian=5). 15
kode dengan `Frequency` kotor (`Baseline`, `Peak`, `Perlu Validasi`) mendapat
`std_opm_frequency = NULL` — nilai tidak ditebak untuk data yang tidak jelas.

Berkas beku `migrations/data/20260729_opm_std_values_v2_19.json` berisi 1138 objek
`{"kode", "importance", "frequency", "criticality"}` (dibangkitkan dari xlsx di atas
oleh skrip ad-hoc yang TIDAK di-commit — `openpyxl` sengaja tidak ditambahkan ke
dependensi backend, mengikuti preseden `cdd92c950f19`) dan **tidak boleh diubah lagi**
setelah revisi ini di-merge — ia masukan tetap bagi `upgrade()`/`downgrade()`.

``upgrade()`` melakukan UPDATE bertarget per `kode` (unique di
`ti_uraian_tugas_jabatan`): ketiga kolom `std_opm_*` diisi **hanya** bila SEMUA tiga
kolom itu saat ini masih `NULL` — baris yang sudah diisi manual (lewat API, sebelum
migrasi ini berjalan) pada salah satu kolom dilewati utuh, tidak ditimpa sebagian.
``downgrade()`` adalah kebalikannya: mengosongkan kembali ke `NULL` **hanya** untuk
baris yang nilai ketiga kolomnya masih persis sama dengan nilai beku (memakai
`IS NOT DISTINCT FROM` untuk `std_opm_frequency` karena boleh `NULL`). Kedua arah aman
dijalankan pada database kosong (0 baris terpengaruh, bukan error) dan mencatat lewat
`logging.warning` sekali bila ada `kode` yang tidak menemukan baris cocok (kode tidak
dipakai jabatan manapun, atau kolomnya sudah terisi nilai lain) — migrasi tidak boleh
gagal karena itu.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "ad595b80d3d1"
down_revision: str | None = "c8fb8be9e184"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

_FROZEN_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "20260729_opm_std_values_v2_19.json"
)

_UPGRADE_SQL = sa.text(
    "UPDATE ti_uraian_tugas_jabatan "
    "SET std_opm_importance = :importance, "
    "    std_opm_frequency = :frequency, "
    "    std_opm_criticality = :criticality "
    "WHERE kode = :kode "
    "AND std_opm_importance IS NULL "
    "AND std_opm_frequency IS NULL "
    "AND std_opm_criticality IS NULL"
)

_DOWNGRADE_SQL = sa.text(
    "UPDATE ti_uraian_tugas_jabatan "
    "SET std_opm_importance = NULL, "
    "    std_opm_frequency = NULL, "
    "    std_opm_criticality = NULL "
    "WHERE kode = :kode "
    "AND std_opm_importance = :importance "
    "AND std_opm_criticality = :criticality "
    "AND std_opm_frequency IS NOT DISTINCT FROM :frequency"
)


def _muat_entri_opm() -> list[dict[str, object]]:
    """Baca berkas beku 1138 entri `{"kode","importance","frequency","criticality"}`.

    Returns:
        list[dict[str, object]]: entri urut menaik menurut `kode`. `frequency` boleh
            `None` untuk 15 kode dengan teks `Frequency` kotor di Task Bank sumber.
    """
    with _FROZEN_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def upgrade() -> None:
    conn = op.get_bind()
    entri = _muat_entri_opm()
    tidak_cocok = 0
    for e in entri:
        result = conn.execute(_UPGRADE_SQL, e)
        if result.rowcount == 0:
            tidak_cocok += 1
    if tidak_cocok:
        logger.warning(
            "Migrasi ad595b80d3d1: %d dari %d entri nilai standar OPM tidak menemukan "
            "baris cocok (kode tak dipakai jabatan manapun, atau salah satu kolom "
            "std_opm_* sudah terisi nilai lain) — dilewati tanpa mengubah data.",
            tidak_cocok,
            len(entri),
        )


def downgrade() -> None:
    conn = op.get_bind()
    entri = _muat_entri_opm()
    tidak_cocok = 0
    for e in entri:
        result = conn.execute(_DOWNGRADE_SQL, e)
        if result.rowcount == 0:
            tidak_cocok += 1
    if tidak_cocok:
        logger.warning(
            "Migrasi ad595b80d3d1 (downgrade): %d dari %d entri tidak menemukan baris "
            "yang nilainya masih persis sama dengan berkas beku — dilewati.",
            tidak_cocok,
            len(entri),
        )
