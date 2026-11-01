"""tambah tabel redesain_kode_orang

Revision ID: 05fdd35204c5
Revises: d2f7e45a1e23
Create Date: 2026-11-01 02:05:35.101867
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "05fdd35204c5"
down_revision: str | None = "d2f7e45a1e23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence("redesain_kode_orang_seq")))
    op.create_table(
        "redesain_kode_orang",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kode", sa.String(length=20), nullable=False),
        sa.Column("partisipan_id", sa.String(length=40), nullable=True),
        sa.Column("keterangan_peran", sa.String(length=200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["partisipan_id"],
            ["partisipan.id"],
            name=op.f("fk_redesain_kode_orang_partisipan_id_partisipan"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_kode_orang")),
        sa.UniqueConstraint("kode", name=op.f("uq_redesain_kode_orang_kode")),
        sa.UniqueConstraint("partisipan_id", name=op.f("uq_redesain_kode_orang_partisipan_id")),
    )


def downgrade() -> None:
    op.drop_table("redesain_kode_orang")
    op.execute(sa.schema.DropSequence(sa.Sequence("redesain_kode_orang_seq")))
