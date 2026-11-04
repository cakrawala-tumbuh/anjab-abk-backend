"""tambah tabel ai_run

Revision ID: d7a2f4c9e1b3
Revises: c5d8e1f3a7b9
Create Date: 2026-11-04 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d7a2f4c9e1b3"
down_revision: str | None = "c5d8e1f3a7b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_run",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fungsi", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=50), nullable=False),
        sa.Column("prompt_hash", sa.String(length=64), nullable=False),
        sa.Column("model_diminta", sa.String(length=100), nullable=False),
        sa.Column("model_dilayani", sa.String(length=100), nullable=True),
        sa.Column("protocol_id", sa.String(length=300), nullable=False),
        sa.Column("input_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("sumber", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("masukan", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("keluaran", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status_qa", sa.String(length=20), nullable=False),
        sa.Column("kode_qa", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stop_reason", sa.String(length=100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("dibuat_oleh", sa.String(length=254), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("selesai_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_run")),
    )
    op.create_index("ix_ai_run_fungsi_status_qa", "ai_run", ["fungsi", "status_qa"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ai_run_fungsi_status_qa", table_name="ai_run")
    op.drop_table("ai_run")
