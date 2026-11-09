"""tambah tabel riset_protokol

Protokol riset berversi yang dapat dikunci permanen (backlog `#119`). Status dibatasi CHECK
`ck_riset_protokol_status` (`DRAF`/`TERKUNCI`); pasangan (`kode`, `versi`) dijaga UNIQUE
`uq_riset_protokol_kode_versi`. `downgrade()` membuang tabel beserta isinya.

Revision ID: 26b72008801d
Revises: 12a4ee50e4f3
Create Date: 2026-11-09 06:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "26b72008801d"
down_revision: str | None = "12a4ee50e4f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "riset_protokol",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kode", sa.String(length=40), nullable=False),
        sa.Column("versi", sa.Integer(), nullable=False),
        sa.Column("judul", sa.String(length=200), nullable=False),
        sa.Column("isi", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'DRAF'"), nullable=False),
        sa.Column("isi_hash", sa.String(length=64), nullable=True),
        sa.Column("dibuat_oleh", sa.String(length=200), nullable=False),
        sa.Column("dikunci_oleh", sa.String(length=200), nullable=True),
        sa.Column("dikunci_pada", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('DRAF', 'TERKUNCI')", name=op.f("ck_riset_protokol_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_riset_protokol")),
        sa.UniqueConstraint("kode", "versi", name="uq_riset_protokol_kode_versi"),
    )


def downgrade() -> None:
    op.drop_table("riset_protokol")
