"""tambah tabel redesain_penilaian

Revision ID: c7f2a9d4e1b3
Revises: b6e1d9f4a2c7
Create Date: 2026-11-01 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7f2a9d4e1b3"
down_revision: str | None = "b6e1d9f4a2c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "redesain_penilaian",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("masalah_id", sa.String(length=36), nullable=False),
        sa.Column("status_bukti", sa.String(length=40), nullable=False),
        sa.Column("gap_material", sa.String(length=40), nullable=False),
        sa.Column("indikasi_kritis", sa.String(length=40), nullable=False),
        sa.Column("k1", sa.String(length=40), nullable=True),
        sa.Column("k2", sa.String(length=40), nullable=True),
        sa.Column("k3", sa.String(length=40), nullable=True),
        sa.Column("k4", sa.String(length=40), nullable=True),
        sa.Column("alasan_rentang_beda", sa.Text(), nullable=True),
        sa.Column("diluruskan_sekolah", sa.Text(), nullable=True),
        sa.Column("pemeriksa_sekolah_konteks", sa.Text(), nullable=True),
        sa.Column("tindak_lanjut", sa.Text(), nullable=True),
        sa.Column("catatan_sumber_versi", sa.Text(), nullable=True),
        sa.Column("saran_otomatis", sa.String(length=20), nullable=True),
        sa.Column("versi_aturan_triase", sa.String(length=10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["masalah_id"], ["redesain_masalah.id"], name="fk_redesain_penilaian_masalah"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_penilaian")),
        sa.UniqueConstraint("masalah_id", name=op.f("uq_redesain_penilaian_masalah_id")),
    )


def downgrade() -> None:
    op.drop_table("redesain_penilaian")
