"""tambah tabel redesain_proses + redesain_langkah

Revision ID: c5d9f13a7b42
Revises: b4e8c2d61f07
Create Date: 2026-11-01 08:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5d9f13a7b42"
down_revision: str | None = "b4e8c2d61f07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "redesain_proses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kode", sa.String(length=20), nullable=False),
        sa.Column("masalah_id", sa.String(length=36), nullable=False),
        sa.Column("sekolah_id", sa.String(length=40), nullable=False),
        sa.Column("periode", sa.String(length=100), nullable=False),
        sa.Column("nama_proses", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["masalah_id"],
            ["redesain_masalah.id"],
            name=op.f("fk_redesain_proses_masalah_id_redesain_masalah"),
        ),
        sa.ForeignKeyConstraint(
            ["sekolah_id"],
            ["sekolah.id"],
            name=op.f("fk_redesain_proses_sekolah_id_sekolah"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_proses")),
        sa.UniqueConstraint("kode", name=op.f("uq_redesain_proses_kode")),
    )
    op.create_index(
        op.f("ix_redesain_proses_masalah_id"), "redesain_proses", ["masalah_id"], unique=False
    )
    op.create_index(
        op.f("ix_redesain_proses_sekolah_id"), "redesain_proses", ["sekolah_id"], unique=False
    )
    op.create_table(
        "redesain_langkah",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("proses_id", sa.String(length=36), nullable=False),
        sa.Column("kode", sa.String(length=20), nullable=False),
        sa.Column("urutan", sa.Integer(), nullable=False),
        sa.Column("tahap", sa.String(length=200), nullable=False),
        sa.Column("pemicu_input", sa.Text(), nullable=False),
        sa.Column("pelaksana", sa.String(length=200), nullable=False),
        sa.Column("pekerjaan_sistem", sa.Text(), nullable=False),
        sa.Column("keluaran_penerima", sa.Text(), nullable=False),
        sa.Column("pemeriksa_pemutus", sa.String(length=200), nullable=True),
        sa.Column("hambatan", sa.Text(), nullable=True),
        sa.Column("status_langkah", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["proses_id"],
            ["redesain_proses.id"],
            name=op.f("fk_redesain_langkah_proses_id_redesain_proses"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_langkah")),
        sa.UniqueConstraint("kode", name=op.f("uq_redesain_langkah_kode")),
    )
    op.create_index(
        op.f("ix_redesain_langkah_proses_id"), "redesain_langkah", ["proses_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_redesain_langkah_proses_id"), table_name="redesain_langkah")
    op.drop_table("redesain_langkah")
    op.drop_index(op.f("ix_redesain_proses_sekolah_id"), table_name="redesain_proses")
    op.drop_index(op.f("ix_redesain_proses_masalah_id"), table_name="redesain_proses")
    op.drop_table("redesain_proses")
