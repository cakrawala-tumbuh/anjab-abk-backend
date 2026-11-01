"""tambah tabel redesain_koreksi_langkah

Revision ID: f4c7d2a9b6e1
Revises: e3b9a6c2f1d8
Create Date: 2026-11-01 11:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4c7d2a9b6e1"
down_revision: str | None = "e3b9a6c2f1d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "redesain_koreksi_langkah",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("langkah_id", sa.String(length=36), nullable=False),
        sa.Column("konfirmasi_id", sa.String(length=36), nullable=True),
        sa.Column("kode_orang", sa.String(length=20), nullable=False),
        sa.Column("isi", sa.Text(), nullable=False),
        sa.Column("waktu", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["langkah_id"], ["redesain_langkah.id"], name="fk_redesain_koreksi_langkah_langkah"
        ),
        sa.ForeignKeyConstraint(
            ["konfirmasi_id"],
            ["redesain_konfirmasi.id"],
            name="fk_redesain_koreksi_langkah_konfirmasi",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_koreksi_langkah")),
    )
    op.create_index(
        op.f("ix_redesain_koreksi_langkah_langkah_id"),
        "redesain_koreksi_langkah",
        ["langkah_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_redesain_koreksi_langkah_langkah_id"), table_name="redesain_koreksi_langkah"
    )
    op.drop_table("redesain_koreksi_langkah")
