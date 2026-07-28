"""selaraskan uraian tugas katalog TI dengan redaksi sederhana v2.19-R1

Revision ID: cdd92c950f19
Revises: 79edf4fa66b1
Create Date: 2026-07-28 15:29:11.035950

Backlog `anjab-abk-backend#30`. Redaksi uraian tugas hasil generasi 5C terbukti
berbelit saat pilot (pola `"<verba> <objek> untuk <alasan>, <cara>, menghasilkan
<output>"` menaruh cara di belakang alasan). Panel bahasa menghasilkan
`Task_Bank_Redaksi_Sederhana_v2_19_R1.xlsx` (sheet `10_Normalisasi`) yang
menyederhanakan redaksi tiap task; dari 1.138 kode yang ada di katalog aplikasi
(`taskinv/data/task_catalog.json`), **740** berstatus `Language_Eligibility_Status
== "ELIGIBLE"` — sisanya (`SPLIT_REQUIRED`/`OUTPUT_UNCLEAR`/dll.) masih menunggu
klarifikasi SME dan **tidak** disentuh migrasi ini.

`task_catalog.json` sudah diperbarui in-place pada commit yang sama (memengaruhi
instalasi BARU lewat `seed_catalog_models`), tetapi `seed_catalog_models`
(`taskinv/seed.py:82`) hanya **membuat** baris yang belum ada — instance yang
sudah berjalan (mis. pilot YPII) tidak ikut terupdate tanpa migrasi data ini.

Berkas beku `migrations/data/20260728_uraian_sederhana_v2_19_r1.json` berisi 740
objek `{"kode", "lama", "baru"}` (dibangkitkan dari xlsx di atas oleh skrip ad-hoc
yang TIDAK di-commit — `openpyxl` sengaja tidak ditambahkan ke dependensi backend)
dan **tidak boleh diubah lagi** setelah revisi ini di-merge — ia masukan tetap
bagi `upgrade()`/`downgrade()`.

``upgrade()`` melakukan UPDATE bertarget per `kode`: `ti_uraian_tugas.uraian`
diganti ke `baru` **hanya** untuk baris yang di-join lewat
`ti_uraian_tugas_jabatan.kode` (unique) **dan** teksnya masih persis `lama` —
syarat kedua ini mencegah menimpa baris yang sudah diedit manual (mis. lewat
usulan Tahap 1 yang dimaterialisasi, entri `[2026-07-26]` `CLAUDE.md`) sejak
katalog di-seed. ``downgrade()`` adalah kebalikannya persis (`baru` -> `lama`,
syarat pencocokan yang sama). Kedua arah aman dijalankan pada database kosong
(0 baris terpengaruh, bukan error) dan mencatat lewat `logging.warning` sekali
bila ada entri yang tidak menemukan baris yang cocok (kode tidak dipakai jabatan
manapun, atau teksnya sudah berubah) — migrasi tidak boleh gagal karena itu.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "cdd92c950f19"
down_revision: str | None = "79edf4fa66b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

_FROZEN_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "20260728_uraian_sederhana_v2_19_r1.json"
)

_UPDATE_SQL = sa.text(
    "UPDATE ti_uraian_tugas SET uraian = :ke "
    "WHERE uraian = :dari "
    "AND id IN (SELECT uraian_tugas_id FROM ti_uraian_tugas_jabatan WHERE kode = :kode)"
)


def _muat_entri_redaksi() -> list[dict[str, str]]:
    """Baca berkas beku 740 entri `{"kode", "lama", "baru"}` dari `migrations/data/`.

    Returns:
        list[dict[str, str]]: entri urut menaik menurut `kode`, masing-masing
            berisi kunci `kode`, `lama` (redaksi 5C asli), dan `baru` (redaksi
            sederhana v2.19-R1). Dipanggil oleh `upgrade()`/`downgrade()` yang
            membedakan arah lewat parameter `dari`/`ke` pada `_terapkan_redaksi`.
    """
    with _FROZEN_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _terapkan_redaksi(
    conn: sa.Connection, entri: list[dict[str, str]], *, dari: str, ke: str
) -> None:
    """Jalankan UPDATE `ti_uraian_tugas.uraian` per entri, `dari` -> `ke`.

    Args:
        conn: koneksi Alembic aktif (`op.get_bind()`).
        entri: daftar `{"kode", "lama", "baru"}` dari `_muat_entri_redaksi()`.
        dari: kunci entri yang dipakai sebagai nilai teks LAMA (syarat WHERE).
            `"lama"` untuk upgrade, `"baru"` untuk downgrade.
        ke: kunci entri yang dipakai sebagai nilai teks BARU (nilai SET).
            `"baru"` untuk upgrade, `"lama"` untuk downgrade.

    Tiap baris di-UPDATE hanya bila `kode` ditemukan di `ti_uraian_tugas_jabatan`
    (unique per kode) DAN teks `ti_uraian_tugas.uraian` saat ini persis sama
    dengan nilai `dari` — baris yang sudah diedit manual atau kode yang tidak
    dipakai jabatan manapun dilewati tanpa error, hanya dihitung sebagai "tidak
    cocok" dan dilaporkan sekali lewat `logger.warning` setelah loop selesai.
    """
    tidak_cocok = 0
    for e in entri:
        result = conn.execute(_UPDATE_SQL, {"ke": e[ke], "dari": e[dari], "kode": e["kode"]})
        if result.rowcount == 0:
            tidak_cocok += 1
    if tidak_cocok:
        logger.warning(
            "Migrasi cdd92c950f19: %d dari %d entri redaksi tidak menemukan baris "
            "cocok (kode tak dipakai jabatan manapun, atau teks sudah berubah dari "
            "nilai '%s' yang diharapkan) — dilewati tanpa mengubah data.",
            tidak_cocok,
            len(entri),
            dari,
        )


def upgrade() -> None:
    conn = op.get_bind()
    entri = _muat_entri_redaksi()
    _terapkan_redaksi(conn, entri, dari="lama", ke="baru")


def downgrade() -> None:
    conn = op.get_bind()
    entri = _muat_entri_redaksi()
    _terapkan_redaksi(conn, entri, dari="baru", ke="lama")
