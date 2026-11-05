"""tambah tabel narasi_ai_permintaan

Revision ID: 97fef4e3d32c
Revises: 4c3a8bab245e
Create Date: 2026-11-05 08:09:06.074625
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "97fef4e3d32c"
down_revision: str | None = "4c3a8bab245e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "narasi_ai_permintaan",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("narasi_id", sa.String(length=36), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("ai_run_id", sa.String(length=36), nullable=False),
        sa.Column("sumber_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("diminta_oleh", sa.String(length=254), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("diserap_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("hasil_serap", sa.String(length=40), nullable=True),
        sa.Column("kode_serap", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(
            ["ai_run_id"], ["ai_run.id"], name="fk_narasi_ai_permintaan_ai_run_id_ai_run"
        ),
        sa.ForeignKeyConstraint(
            ["narasi_id"],
            ["narasi_kasus.id"],
            name="fk_narasi_ai_permintaan_narasi_id_narasi_kasus",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_narasi_ai_permintaan")),
        sa.UniqueConstraint("ai_run_id", name=op.f("uq_narasi_ai_permintaan_ai_run_id")),
    )
    op.create_index(
        "ix_narasi_ai_permintaan_belum_diserap",
        "narasi_ai_permintaan",
        ["narasi_id"],
        unique=False,
        postgresql_where=sa.text("diserap_at IS NULL"),
    )
    op.create_index(
        "ix_narasi_ai_permintaan_narasi_id_created_at",
        "narasi_ai_permintaan",
        ["narasi_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_narasi_ai_permintaan_narasi_id_created_at", table_name="narasi_ai_permintaan")
    op.drop_index(
        "ix_narasi_ai_permintaan_belum_diserap",
        table_name="narasi_ai_permintaan",
        postgresql_where=sa.text("diserap_at IS NULL"),
    )
    op.drop_table("narasi_ai_permintaan")
