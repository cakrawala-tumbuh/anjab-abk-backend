"""ti_sesi ganti periode jadi cabang hapus min max responden

Revision ID: 08b6b999ee05
Revises: 3b10e24fa970
Create Date: 2026-07-15 03:05:48.065232

Task Inventory (`TiSesi`): field `periode` (string bebas `YYYY-MM`) diganti
`cabang` (enum aplikasi 2 nilai `"Bandung"`/`"Semarang"`, disimpan sebagai
`String(20)` — konsisten dengan `status`). `min_responden`/`max_responden`
dihapus total: TI tidak lagi punya batas atas jumlah responden (mengikuti
keputusan yang sama yang sudah diambil untuk DCS/WCP, revisi `3b10e24fa970`).

**Kolom `cabang` sengaja `nullable=True` — TIDAK ADA backfill.** Baris `ti_sesi`
produksi lama (dibuat sebelum revisi ini) akan punya `cabang = NULL`; nilai
Bandung/Semarang yang benar untuk baris-baris itu tidak dapat ditebak dari data
yang ada (YPII punya kedua cabang) dan BUTUH keputusan admin per-baris di luar
cakupan migrasi ini. `TiSesiRead.cabang`/`TiSesiCreate.cabang` mengikuti:
Create tetap WAJIB (sesi baru selalu punya cabang), Read Optional (baris lama
bisa NULL).

Downgrade best-effort (mengikuti konvensi `3b10e24fa970`): `periode` dipulihkan
`nullable=True` (nilai lama tidak direkonstruksi), `min_responden`/
`max_responden` dipulihkan dengan default lama (3/10) agar baris existing tidak
menyisakan NULL pada kolom yang tadinya NOT NULL.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "08b6b999ee05"
down_revision: str | None = "3b10e24fa970"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `cabang` nullable=True SENGAJA — tanpa backfill (lihat docstring modul).
    op.add_column("ti_sesi", sa.Column("cabang", sa.String(length=20), nullable=True))
    op.drop_column("ti_sesi", "min_responden")
    op.drop_column("ti_sesi", "max_responden")
    op.drop_column("ti_sesi", "periode")


def downgrade() -> None:
    # Best-effort: nilai lama tidak direkonstruksi. `periode` nullable=True
    # (konvensi `3b10e24fa970`); `min_responden`/`max_responden` dipulihkan
    # dengan server_default = default lama (3/10) supaya baris existing tidak
    # menyisakan NULL pada kolom yang tadinya NOT NULL.
    op.add_column(
        "ti_sesi", sa.Column("periode", sa.VARCHAR(length=7), autoincrement=False, nullable=True)
    )
    op.add_column(
        "ti_sesi",
        sa.Column(
            "max_responden",
            sa.INTEGER(),
            autoincrement=False,
            nullable=False,
            server_default="10",
        ),
    )
    op.add_column(
        "ti_sesi",
        sa.Column(
            "min_responden",
            sa.INTEGER(),
            autoincrement=False,
            nullable=False,
            server_default="3",
        ),
    )
    op.drop_column("ti_sesi", "cabang")
