"""tambah tabel redesain_konteks

Revision ID: a7c3e91b4d20
Revises: 05fdd35204c5
Create Date: 2026-11-01 04:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7c3e91b4d20"
down_revision: str | None = "05fdd35204c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "redesain_konteks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kode", sa.String(length=10), nullable=False),
        sa.Column("tema", sa.String(length=200), nullable=False),
        sa.Column("gelombang", sa.String(length=40), nullable=False),
        sa.Column("ruang_dugaan", sa.Text(), nullable=False),
        sa.Column("sumber_draft", sa.Text(), nullable=False),
        sa.Column("batas_pemeriksaan", sa.Text(), nullable=False),
        sa.Column("aktif", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_konteks")),
        sa.UniqueConstraint("kode", name=op.f("uq_redesain_konteks_kode")),
    )


def downgrade() -> None:
    op.drop_table("redesain_konteks")
