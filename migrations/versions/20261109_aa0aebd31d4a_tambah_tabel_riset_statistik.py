"""tambah tabel riset_statistik

Keluaran analisis statistik per protokol riset terkunci beserta verifikasi independen
(backlog `#122`). Status dibatasi CHECK `ck_riset_statistik_status` (`DRAF`/`TERVERIFIKASI`);
`protokol_id` FK ke `riset_protokol.id` `ON DELETE RESTRICT` dan berindeks.
`downgrade()` membuang indeks dan tabel beserta isinya.

Revision ID: aa0aebd31d4a
Revises: 26b72008801d
Create Date: 2026-11-09 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "aa0aebd31d4a"
down_revision: str | None = "26b72008801d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "riset_statistik",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("protokol_id", sa.String(length=36), nullable=False),
        sa.Column("nama_analisis", sa.String(length=200), nullable=False),
        sa.Column("keluaran", sa.Text(), nullable=False),
        sa.Column("kode_sumber_ref", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'DRAF'"), nullable=False),
        sa.Column("dibuat_oleh", sa.String(length=200), nullable=False),
        sa.Column("diverifikasi_oleh", sa.String(length=200), nullable=True),
        sa.Column("diverifikasi_pada", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAF', 'TERVERIFIKASI')", name=op.f("ck_riset_statistik_status")
        ),
        sa.ForeignKeyConstraint(
            ["protokol_id"],
            ["riset_protokol.id"],
            name=op.f("fk_riset_statistik_protokol_id_riset_protokol"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_riset_statistik")),
    )
    op.create_index(
        op.f("ix_riset_statistik_protokol_id"), "riset_statistik", ["protokol_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_riset_statistik_protokol_id"), table_name="riset_statistik")
    op.drop_table("riset_statistik")
