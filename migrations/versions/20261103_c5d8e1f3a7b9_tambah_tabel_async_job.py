"""tambah tabel async_job

Revision ID: c5d8e1f3a7b9
Revises: b3e8f1c5a7d2
Create Date: 2026-11-03 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5d8e1f3a7b9"
down_revision: str | None = "b3e8f1c5a7d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "async_job",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("fitur", sa.String(length=50), nullable=False),
        sa.Column("jenis", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("ref_id", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("percobaan", sa.Integer(), nullable=False),
        sa.Column("dibuat_oleh", sa.String(length=254), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_async_job")),
    )
    op.create_index("ix_async_job_fitur_status", "async_job", ["fitur", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_async_job_fitur_status", table_name="async_job")
    op.drop_table("async_job")
