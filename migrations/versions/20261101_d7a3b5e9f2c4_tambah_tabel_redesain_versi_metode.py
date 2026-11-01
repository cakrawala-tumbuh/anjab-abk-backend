"""tambah tabel redesain_versi_metode

Revision ID: d7a3b5e9f2c4
Revises: c6f9a2d4e8b1
Create Date: 2026-11-01 16:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7a3b5e9f2c4"
down_revision: str | None = "c6f9a2d4e8b1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "redesain_versi_metode",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("versi", sa.String(length=20), nullable=False),
        sa.Column("tanggal", sa.Date(), nullable=False),
        sa.Column("bagian", sa.String(length=200), nullable=False),
        sa.Column("apa_diperbarui", sa.Text(), nullable=False),
        sa.Column("alasan_risiko", sa.Text(), nullable=False),
        sa.Column("status_hasil_uji", sa.Text(), nullable=False),
        sa.Column("pemeriksa_pemutus", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_versi_metode")),
        sa.UniqueConstraint("versi", "bagian", name="uq_redesain_versi_metode_versi_bagian"),
    )
    op.create_index(
        op.f("ix_redesain_versi_metode_versi"), "redesain_versi_metode", ["versi"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_redesain_versi_metode_versi"), table_name="redesain_versi_metode")
    op.drop_table("redesain_versi_metode")
