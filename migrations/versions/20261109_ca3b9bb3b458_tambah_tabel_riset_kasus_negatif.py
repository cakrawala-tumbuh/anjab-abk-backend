"""tambah tabel riset_kasus_negatif

Kasus negatif (kasus yang tidak mendukung hipotesis) per protokol riset terkunci, append-only
(backlog `#123`). `protokol_id` FK ke `riset_protokol.id` `ON DELETE RESTRICT` dan berindeks.
`downgrade()` membuang indeks dan tabel beserta isinya.

Revision ID: ca3b9bb3b458
Revises: aa0aebd31d4a
Create Date: 2026-11-09 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ca3b9bb3b458"
down_revision: str | None = "aa0aebd31d4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "riset_kasus_negatif",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("protokol_id", sa.String(length=36), nullable=False),
        sa.Column("ringkasan", sa.Text(), nullable=False),
        sa.Column("alasan_negatif", sa.Text(), nullable=False),
        sa.Column("sumber_ref", sa.String(length=500), nullable=True),
        sa.Column("dibuat_oleh", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["protokol_id"],
            ["riset_protokol.id"],
            name=op.f("fk_riset_kasus_negatif_protokol_id_riset_protokol"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_riset_kasus_negatif")),
    )
    op.create_index(
        op.f("ix_riset_kasus_negatif_protokol_id"),
        "riset_kasus_negatif",
        ["protokol_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_riset_kasus_negatif_protokol_id"), table_name="riset_kasus_negatif")
    op.drop_table("riset_kasus_negatif")
