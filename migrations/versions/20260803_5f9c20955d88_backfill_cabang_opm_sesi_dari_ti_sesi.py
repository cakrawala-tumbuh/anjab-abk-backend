"""backfill cabang opm_sesi dari ti_sesi sumber

Revision ID: 5f9c20955d88
Revises: 981b2e1945b0
Create Date: 2026-08-03 13:30:00.000000

Backlog `anjab-abk-backend#37`, lanjutan langsung `981b2e1945b0` (disiplin satu
perubahan/berkas: DDL lalu data). Sesi OPM baru selalu mendapat `cabang` dari
`SqlOpmSesiService.create()` (diturunkan dari `ti_sesi.cabang`), tetapi 3 sesi OPM
produksi YPII yang sudah ada sebelum revisi ini punya `cabang IS NULL` — semuanya
bersumber dari sesi TI cabang Semarang (`opses_55920bbd`→`tises_e04896d4`,
`opses_492c79e9`→`tises_43c2bf69`, `opses_851fa231`→`tises_bb3ace43`, diverifikasi
lewat MCP 2026-08-03), dua di antaranya sudah punya jawaban ter-submit.

`upgrade()`: `UPDATE opm_sesi SET cabang = ti_sesi.cabang FROM ti_sesi WHERE
ti_sesi.id = opm_sesi.ti_sesi_id AND opm_sesi.cabang IS NULL AND ti_sesi.cabang IS
NOT NULL` — idempoten (baris yang `cabang`-nya sudah terisi TIDAK ditimpa), dan TIDAK
menyentuh baris yang `ti_sesi` sumbernya sendiri `cabang IS NULL` (tidak ada nilai
untuk dibackfill; tetap `NULL`, bukan error). **Tidak ada `DELETE` di revisi ini** —
jumlah baris `opm_sesi`/`opm_responden`/`opm_jawaban` tidak berkurang sebaris pun.

`downgrade()` adalah kebalikannya: mengosongkan kembali ke `NULL` **hanya** untuk
baris yang `opm_sesi.cabang` saat itu masih PERSIS sama dengan `ti_sesi.cabang`
sumbernya (mencegah menimpa nilai yang sengaja diubah manual setelah migrasi ini
berjalan). Aman dijalankan di database kosong (0 baris terpengaruh, bukan error);
jumlah baris yang ter-update dicatat lewat `logging.info` di kedua arah.
"""

from __future__ import annotations

from collections.abc import Sequence
from logging import getLogger

import sqlalchemy as sa
from alembic import op

revision: str = "5f9c20955d88"
down_revision: str | None = "981b2e1945b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = getLogger(__name__)

_UPGRADE_SQL = sa.text(
    "UPDATE opm_sesi "
    "SET cabang = ti_sesi.cabang "
    "FROM ti_sesi "
    "WHERE ti_sesi.id = opm_sesi.ti_sesi_id "
    "AND opm_sesi.cabang IS NULL "
    "AND ti_sesi.cabang IS NOT NULL"
)

_DOWNGRADE_SQL = sa.text(
    "UPDATE opm_sesi "
    "SET cabang = NULL "
    "FROM ti_sesi "
    "WHERE ti_sesi.id = opm_sesi.ti_sesi_id "
    "AND opm_sesi.cabang IS NOT NULL "
    "AND opm_sesi.cabang = ti_sesi.cabang"
)


def upgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(_UPGRADE_SQL)
    logger.info(
        "Migrasi 5f9c20955d88: %d baris opm_sesi di-backfill cabang dari ti_sesi sumber.",
        result.rowcount,
    )


def downgrade() -> None:
    conn = op.get_bind()
    result = conn.execute(_DOWNGRADE_SQL)
    logger.info(
        "Migrasi 5f9c20955d88 (downgrade): %d baris opm_sesi dikosongkan kembali ke cabang NULL.",
        result.rowcount,
    )
