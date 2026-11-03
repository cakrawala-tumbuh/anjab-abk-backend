"""tambah tabel opm_sesi_pengecualian

Revision ID: a9c4e7b2d6f1
Revises: d7a3b5e9f2c4
Create Date: 2026-11-03 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9c4e7b2d6f1"
down_revision: str | None = "d7a3b5e9f2c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "opm_sesi_pengecualian",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sesi_id", sa.String(length=40), nullable=False),
        sa.Column("task_kode", sa.String(length=20), nullable=False),
        sa.Column("alasan", sa.String(length=40), nullable=False),
        sa.Column("keterangan", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="OPEN", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sesi_id"],
            ["opm_sesi.id"],
            name="fk_opm_sesi_pengecualian_sesi",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opm_sesi_pengecualian")),
        sa.UniqueConstraint(
            "sesi_id",
            "task_kode",
            "alasan",
            name="uq_opm_sesi_pengecualian_sesi_task_alasan",
        ),
    )
    op.create_index(
        op.f("ix_opm_sesi_pengecualian_sesi_id"),
        "opm_sesi_pengecualian",
        ["sesi_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_opm_sesi_pengecualian_sesi_id"), table_name="opm_sesi_pengecualian")
    op.drop_table("opm_sesi_pengecualian")
