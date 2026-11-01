"""tambah tabel redesain_sesi dan redesain_sesi_masalah

Revision ID: b5e8f1c3d7a2
Revises: a9d4c6e2b8f3
Create Date: 2026-11-01 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b5e8f1c3d7a2"
down_revision: str | None = "a9d4c6e2b8f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "redesain_sesi",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kode_sesi", sa.String(length=20), nullable=False),
        sa.Column("kode_orang", sa.String(length=20), nullable=False),
        sa.Column("sekolah_id", sa.String(length=40), nullable=True),
        sa.Column("peran", sa.String(length=200), nullable=False),
        sa.Column("jenis_kegiatan", sa.String(length=40), nullable=False),
        sa.Column("menit_rencana", sa.Integer(), nullable=True),
        sa.Column("menit_disepakati", sa.Integer(), nullable=True),
        sa.Column("waktu_kalender", sa.Text(), nullable=True),
        sa.Column("catatan", sa.Text(), nullable=True),
        sa.Column(
            "status_izin",
            sa.String(length=40),
            server_default="Belum ditetapkan",
            nullable=False,
        ),
        sa.Column("versi_izin", sa.String(length=50), nullable=True),
        sa.Column("pic_kode_orang", sa.String(length=20), nullable=True),
        sa.Column("tindak_lanjut", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sekolah_id"], ["sekolah.id"], name="fk_redesain_sesi_sekolah", ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_sesi")),
        sa.UniqueConstraint(
            "kode_sesi", "kode_orang", name="uq_redesain_sesi_kode_sesi_kode_orang"
        ),
    )
    op.create_index(
        op.f("ix_redesain_sesi_kode_sesi"), "redesain_sesi", ["kode_sesi"], unique=False
    )
    op.create_index(
        op.f("ix_redesain_sesi_kode_orang"), "redesain_sesi", ["kode_orang"], unique=False
    )
    op.create_index(
        op.f("ix_redesain_sesi_sekolah_id"), "redesain_sesi", ["sekolah_id"], unique=False
    )
    op.create_table(
        "redesain_sesi_masalah",
        sa.Column("sesi_id", sa.String(length=36), nullable=False),
        sa.Column("masalah_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(
            ["sesi_id"],
            ["redesain_sesi.id"],
            name="fk_redesain_sesi_masalah_sesi",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["masalah_id"],
            ["redesain_masalah.id"],
            name="fk_redesain_sesi_masalah_masalah",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("sesi_id", "masalah_id", name=op.f("pk_redesain_sesi_masalah")),
    )
    op.create_index(
        op.f("ix_redesain_sesi_masalah_masalah_id"),
        "redesain_sesi_masalah",
        ["masalah_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_redesain_sesi_masalah_masalah_id"), table_name="redesain_sesi_masalah")
    op.drop_table("redesain_sesi_masalah")
    op.drop_index(op.f("ix_redesain_sesi_sekolah_id"), table_name="redesain_sesi")
    op.drop_index(op.f("ix_redesain_sesi_kode_orang"), table_name="redesain_sesi")
    op.drop_index(op.f("ix_redesain_sesi_kode_sesi"), table_name="redesain_sesi")
    op.drop_table("redesain_sesi")
