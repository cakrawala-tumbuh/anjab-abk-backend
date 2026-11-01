"""tambah tabel redesain_masalah + redesain_masalah_uraian_tugas

Revision ID: b4e8c2d61f07
Revises: a7c3e91b4d20
Create Date: 2026-11-01 06:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b4e8c2d61f07"
down_revision: str | None = "a7c3e91b4d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "redesain_masalah",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kode", sa.String(length=20), nullable=False),
        sa.Column("konteks_id", sa.String(length=36), nullable=False),
        sa.Column("sekolah_id", sa.String(length=40), nullable=True),
        sa.Column("keterangan_sekolah", sa.String(length=200), nullable=True),
        sa.Column("periode_acuan", sa.String(length=100), nullable=False),
        sa.Column("periode_pasti", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("rumusan_hipotesis", sa.Text(), nullable=False),
        sa.Column("sumber_awal_keterbatasan", sa.Text(), nullable=False),
        sa.Column("status_awal", sa.String(length=40), nullable=False),
        sa.Column("gelombang", sa.String(length=40), nullable=False),
        sa.Column("penjelasan_alternatif", sa.Text(), nullable=True),
        sa.Column("pic_kode_orang", sa.String(length=20), nullable=True),
        sa.Column(
            "dibuka_untuk_konfirmasi",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("status_awal_dibekukan_pada", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["konteks_id"],
            ["redesain_konteks.id"],
            name=op.f("fk_redesain_masalah_konteks_id_redesain_konteks"),
        ),
        sa.ForeignKeyConstraint(
            ["sekolah_id"],
            ["sekolah.id"],
            name=op.f("fk_redesain_masalah_sekolah_id_sekolah"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_masalah")),
        sa.UniqueConstraint("kode", name=op.f("uq_redesain_masalah_kode")),
    )
    op.create_index(
        op.f("ix_redesain_masalah_konteks_id"), "redesain_masalah", ["konteks_id"], unique=False
    )
    op.create_index(
        op.f("ix_redesain_masalah_sekolah_id"), "redesain_masalah", ["sekolah_id"], unique=False
    )
    op.create_table(
        "redesain_masalah_uraian_tugas",
        sa.Column("masalah_id", sa.String(length=36), nullable=False),
        sa.Column("uraian_tugas_id", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["masalah_id"],
            ["redesain_masalah.id"],
            name=op.f("fk_redesain_masalah_uraian_tugas_masalah_id_redesain_masalah"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["uraian_tugas_id"],
            ["ti_uraian_tugas.id"],
            name="fk_redesain_masalah_ut_uraian_tugas_id_ti_uraian_tugas",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "masalah_id", "uraian_tugas_id", name=op.f("pk_redesain_masalah_uraian_tugas")
        ),
    )
    op.create_index(
        op.f("ix_redesain_masalah_uraian_tugas_uraian_tugas_id"),
        "redesain_masalah_uraian_tugas",
        ["uraian_tugas_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_redesain_masalah_uraian_tugas_uraian_tugas_id"),
        table_name="redesain_masalah_uraian_tugas",
    )
    op.drop_table("redesain_masalah_uraian_tugas")
    op.drop_index(op.f("ix_redesain_masalah_sekolah_id"), table_name="redesain_masalah")
    op.drop_index(op.f("ix_redesain_masalah_konteks_id"), table_name="redesain_masalah")
    op.drop_table("redesain_masalah")
