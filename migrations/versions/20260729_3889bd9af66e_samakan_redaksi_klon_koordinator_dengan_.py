"""samakan redaksi klon jabatan Koordinator dengan kembarannya di katalog

Revision ID: 3889bd9af66e
Revises: cdd92c950f19
Create Date: 2026-07-29 09:12:44.618203

Lanjutan `cdd92c950f19`. Instance pilot YPII memuat **124 baris katalog di luar**
`taskinv/data/task_catalog.json` (1.138 kode): `KOEKS-*` (46), `KOHUM-*` (29),
`KOSAR-*` (49) — jabatan `Koordinator Ekstrakurikuler`/`Koordinator Humas`/
`Koordinator Sarana Prasarana`, nomenklatur cabang Bandung. Baris itu dibuat
manual pada 2026-07-12 (~20.00 WIB, setelah seed katalog 18.47) dengan cara
**menyalin uraian tugas dari jabatan kembarannya** di nomenklatur Semarang
(`PEK-*`, `WKHUM-*`, `WKSAR-*`); sufiks kode kedua sisi identik, jadi
pasangannya deterministik (`PEK-ALL-ADMIN-005` ↔ `KOEKS-ALL-ADMIN-005`).

Karena kode `KO*` tidak ada di `task_catalog.json` **maupun** di
`Task_Bank_Redaksi_Sederhana_v2_19_R1.xlsx`, `cdd92c950f19` (mencocokkan per
`kode`) melewati semuanya. Akibatnya 75 baris klon masih memakai redaksi 5C
lama sementara kembarannya sudah disederhanakan — dua cabang membaca kalimat
berbeda untuk tugas yang sama. Revisi ini menyamakan 75 baris itu.

Berkas beku `migrations/data/20260729_uraian_klon_koordinator_v2_19_r1.json`
berisi 75 objek `{"kode", "kembaran", "lama", "baru"}` (`lama`/`baru` disalin
dari nilai kembarannya sebelum/sesudah `cdd92c950f19`) dan **tidak boleh diubah
lagi** setelah revisi ini di-merge — ia masukan tetap bagi
`upgrade()`/`downgrade()`. `kembaran` murni jejak asal-usul; yang dipakai SQL
hanya `kode`/`lama`/`baru`.

Mekanismenya sama persis dengan `cdd92c950f19`: UPDATE bertarget per `kode`,
di-join lewat `ti_uraian_tugas_jabatan.kode` (unique) **dan** hanya bila teksnya
masih persis `lama` — baris yang sudah diedit manual tidak tertimpa.
``downgrade()`` kebalikannya persis. Aman dijalankan pada database kosong
(0 baris terpengaruh, bukan error); entri yang tidak menemukan baris cocok
dicatat sekali lewat `logging.warning`, tidak menggagalkan migrasi.

**Yang TIDAK dilakukan:** ketiga jabatan `Koordinator …` tetap **tidak**
dimasukkan ke `task_catalog.json` — instalasi baru tetap tidak memilikinya
(status quo sejak 2026-07-12), dan perubahan redaksi berikutnya akan melewatinya
lagi dengan pola yang sama. Memasukkannya ke katalog seed adalah keputusan
produk tersendiri, di luar lingkup revisi ini.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "3889bd9af66e"
down_revision: str | None = "cdd92c950f19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = logging.getLogger(__name__)

_FROZEN_PATH = (
    Path(__file__).resolve().parent.parent
    / "data"
    / "20260729_uraian_klon_koordinator_v2_19_r1.json"
)

_UPDATE_SQL = sa.text(
    "UPDATE ti_uraian_tugas SET uraian = :ke "
    "WHERE uraian = :dari "
    "AND id IN (SELECT uraian_tugas_id FROM ti_uraian_tugas_jabatan WHERE kode = :kode)"
)


def _muat_entri_klon() -> list[dict[str, str]]:
    """Baca berkas beku 75 entri `{"kode", "kembaran", "lama", "baru"}` dari `migrations/data/`.

    Returns:
        list[dict[str, str]]: entri urut menaik menurut `kode`, masing-masing
            berisi `kode` (kode klon `KOEKS-`/`KOHUM-`/`KOSAR-`), `kembaran`
            (kode sumber salinan di katalog), `lama` (redaksi 5C asli), dan
            `baru` (redaksi sederhana v2.19-R1 milik kembarannya). Dipanggil
            `upgrade()`/`downgrade()` yang membedakan arah lewat parameter
            `dari`/`ke` pada `_terapkan_redaksi`.
    """
    with _FROZEN_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _terapkan_redaksi(
    conn: sa.Connection, entri: list[dict[str, str]], *, dari: str, ke: str
) -> None:
    """Jalankan UPDATE `ti_uraian_tugas.uraian` per entri klon, `dari` -> `ke`.

    Args:
        conn: koneksi Alembic aktif (`op.get_bind()`).
        entri: daftar entri klon dari `_muat_entri_klon()`.
        dari: kunci entri yang dipakai sebagai nilai teks LAMA (syarat WHERE).
            `"lama"` untuk upgrade, `"baru"` untuk downgrade.
        ke: kunci entri yang dipakai sebagai nilai teks BARU (nilai SET).
            `"baru"` untuk upgrade, `"lama"` untuk downgrade.

    Sama seperti `cdd92c950f19`: baris di-UPDATE hanya bila `kode` ditemukan di
    `ti_uraian_tugas_jabatan` DAN teks `uraian` saat ini persis sama dengan
    nilai `dari`. Baris yang sudah diedit manual atau kode yang tidak dipakai
    jabatan manapun (mis. instalasi baru yang memang tidak punya jabatan
    `Koordinator …`) dilewati tanpa error, dihitung sebagai "tidak cocok" dan
    dilaporkan sekali lewat `logger.warning` setelah loop selesai.
    """
    tidak_cocok = 0
    for e in entri:
        result = conn.execute(_UPDATE_SQL, {"ke": e[ke], "dari": e[dari], "kode": e["kode"]})
        if result.rowcount == 0:
            tidak_cocok += 1
    if tidak_cocok:
        logger.warning(
            "Migrasi 3889bd9af66e: %d dari %d entri klon tidak menemukan baris cocok "
            "(kode tak dipakai jabatan manapun, atau teks sudah berubah dari nilai "
            "'%s' yang diharapkan) — dilewati tanpa mengubah data.",
            tidak_cocok,
            len(entri),
            dari,
        )


def upgrade() -> None:
    conn = op.get_bind()
    entri = _muat_entri_klon()
    _terapkan_redaksi(conn, entri, dari="lama", ke="baru")


def downgrade() -> None:
    conn = op.get_bind()
    entri = _muat_entri_klon()
    _terapkan_redaksi(conn, entri, dari="baru", ke="lama")
