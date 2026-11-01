"""tambah kolom keputusan & status pada redesain_penilaian

Revision ID: d8a3e5b7c9f2
Revises: c7f2a9d4e1b3
Create Date: 2026-11-01 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8a3e5b7c9f2"
down_revision: str | None = "c7f2a9d4e1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("redesain_penilaian", sa.Column("prioritas_final", sa.String(20), nullable=True))
    op.add_column("redesain_penilaian", sa.Column("alasan_final", sa.Text(), nullable=True))
    op.add_column(
        "redesain_penilaian", sa.Column("pemutus_kode_orang", sa.String(20), nullable=True)
    )
    op.add_column("redesain_penilaian", sa.Column("pemutus_jabatan", sa.String(200), nullable=True))
    op.add_column("redesain_penilaian", sa.Column("tanggal_keputusan", sa.Date(), nullable=True))
    op.add_column(
        "redesain_penilaian", sa.Column("saran_saat_keputusan", sa.String(20), nullable=True)
    )
    op.add_column(
        "redesain_penilaian",
        sa.Column(
            "status_penilaian",
            sa.String(40),
            nullable=False,
            server_default=sa.text("'Belum ditelaah'"),
        ),
    )


def downgrade() -> None:
    for kolom in (
        "status_penilaian",
        "saran_saat_keputusan",
        "tanggal_keputusan",
        "pemutus_jabatan",
        "pemutus_kode_orang",
        "alasan_final",
        "prioritas_final",
    ):
        op.drop_column("redesain_penilaian", kolom)
