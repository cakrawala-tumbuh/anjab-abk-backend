"""tambah tabel redesain_alternatif

Revision ID: a9d4c6e2b8f3
Revises: d8a3e5b7c9f2
Create Date: 2026-11-01 13:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9d4c6e2b8f3"
down_revision: str | None = "d8a3e5b7c9f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "redesain_alternatif",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("kode", sa.String(length=20), nullable=False),
        sa.Column("masalah_id", sa.String(length=36), nullable=False),
        sa.Column("opsi", sa.String(length=40), nullable=False),
        sa.Column("alur_kini_vs_usulan", sa.Text(), nullable=False),
        sa.Column("pihak_asal_jabatan_id", sa.String(length=40), nullable=True),
        sa.Column("pihak_penerima_jabatan_id", sa.String(length=40), nullable=True),
        sa.Column("komitmen_penerima", sa.Text(), nullable=True),
        sa.Column("jadwal_puncak", sa.Text(), nullable=True),
        sa.Column("keterampilan_akses", sa.Text(), nullable=True),
        sa.Column("tambahan_bersih", sa.Text(), nullable=True),
        sa.Column("risiko_layanan", sa.Text(), nullable=True),
        sa.Column(
            "gap_penerima", sa.String(length=40), server_default="Belum tahu", nullable=False
        ),
        sa.Column(
            "status_telaah", sa.String(length=40), server_default="Belum ditelaah", nullable=False
        ),
        sa.Column("pemutus_kode_orang", sa.String(length=20), nullable=True),
        sa.Column("keputusan", sa.Text(), nullable=True),
        sa.Column("prasyarat_monitoring", sa.Text(), nullable=True),
        sa.Column("catatan_versi_bukti", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["masalah_id"], ["redesain_masalah.id"], name="fk_redesain_alternatif_masalah"
        ),
        sa.ForeignKeyConstraint(
            ["pihak_asal_jabatan_id"], ["jabatan.id"], name="fk_redesain_alternatif_pihak_asal"
        ),
        sa.ForeignKeyConstraint(
            ["pihak_penerima_jabatan_id"],
            ["jabatan.id"],
            name="fk_redesain_alternatif_pihak_penerima",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_alternatif")),
        sa.UniqueConstraint("kode", name=op.f("uq_redesain_alternatif_kode")),
    )
    op.create_index(
        op.f("ix_redesain_alternatif_masalah_id"),
        "redesain_alternatif",
        ["masalah_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_redesain_alternatif_masalah_id"), table_name="redesain_alternatif")
    op.drop_table("redesain_alternatif")
