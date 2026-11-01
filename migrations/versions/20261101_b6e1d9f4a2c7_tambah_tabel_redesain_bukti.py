"""tambah tabel redesain_bukti

Revision ID: b6e1d9f4a2c7
Revises: a5d8c3e7b2f9
Create Date: 2026-11-01 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6e1d9f4a2c7"
down_revision: str | None = "a5d8c3e7b2f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "redesain_bukti",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kode", sa.String(length=20), nullable=False),
        sa.Column("masalah_id", sa.String(length=36), nullable=False),
        sa.Column("langkah_id", sa.String(length=36), nullable=True),
        sa.Column("unit_periode", sa.String(length=200), nullable=False),
        sa.Column("jenis", sa.String(length=40), nullable=False),
        sa.Column("pembuat_kode_orang", sa.String(length=20), nullable=True),
        sa.Column("pembuat_peran", sa.String(length=200), nullable=True),
        sa.Column("independen", sa.String(length=40), nullable=False),
        sa.Column("klaim_didukung", sa.Text(), nullable=False),
        sa.Column("klaim_tidak_didukung", sa.Text(), nullable=True),
        sa.Column("tanggal_versi_lokasi", sa.Text(), nullable=False),
        sa.Column(
            "status_pemeriksaan",
            sa.String(length=40),
            server_default="Belum diperiksa",
            nullable=False,
        ),
        sa.Column("pemeriksa_kode_orang", sa.String(length=20), nullable=True),
        sa.Column("alasan", sa.Text(), nullable=True),
        sa.Column("catatan_privasi_gap", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["masalah_id"], ["redesain_masalah.id"], name="fk_redesain_bukti_masalah"
        ),
        sa.ForeignKeyConstraint(
            ["langkah_id"], ["redesain_langkah.id"], name="fk_redesain_bukti_langkah"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_bukti")),
        sa.UniqueConstraint("kode", name=op.f("uq_redesain_bukti_kode")),
    )
    op.create_index(
        op.f("ix_redesain_bukti_masalah_id"), "redesain_bukti", ["masalah_id"], unique=False
    )
    op.create_index(
        op.f("ix_redesain_bukti_langkah_id"), "redesain_bukti", ["langkah_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_redesain_bukti_langkah_id"), table_name="redesain_bukti")
    op.drop_index(op.f("ix_redesain_bukti_masalah_id"), table_name="redesain_bukti")
    op.drop_table("redesain_bukti")
