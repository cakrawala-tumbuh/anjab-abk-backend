"""tambah tabel ai_saklar_event

Revision ID: e4b8c1d6a2f9
Revises: d7a2f4c9e1b3
Create Date: 2026-11-04 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4b8c1d6a2f9"
down_revision: str | None = "d7a2f4c9e1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_saklar_event",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("layanan", sa.String(length=50), nullable=False),
        sa.Column("aksi", sa.String(length=10), nullable=False),
        sa.Column("alasan", sa.Text(), nullable=False),
        sa.Column("aktor", sa.String(length=254), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_saklar_event")),
    )
    op.create_index(
        "ix_ai_saklar_event_layanan_created_at",
        "ai_saklar_event",
        ["layanan", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_ai_saklar_event_layanan_created_at", table_name="ai_saklar_event")
    op.drop_table("ai_saklar_event")
