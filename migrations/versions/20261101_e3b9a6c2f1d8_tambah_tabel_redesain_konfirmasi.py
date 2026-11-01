"""tambah tabel redesain_konfirmasi + kolom redesain_masalah.eskalasi_pada

Revision ID: e3b9a6c2f1d8
Revises: c5d9f13a7b42
Create Date: 2026-11-01 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3b9a6c2f1d8"
down_revision: str | None = "c5d9f13a7b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "redesain_masalah",
        sa.Column("eskalasi_pada", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "redesain_konfirmasi",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("masalah_id", sa.String(length=36), nullable=False),
        sa.Column("kode_orang", sa.String(length=20), nullable=False),
        sa.Column("sekolah_id", sa.String(length=40), nullable=False),
        sa.Column(
            "sumber", sa.String(length=40), server_default=sa.text("'daring'"), nullable=False
        ),
        sa.Column("peran", sa.String(length=200), nullable=True),
        sa.Column("tanggal", sa.Date(), nullable=False),
        sa.Column("cerita_sebelum", sa.Text(), nullable=True),
        sa.Column("cerita_dikunci_pada", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dugaan_ditampilkan_pada", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dikirim_pada", sa.DateTime(timezone=True), nullable=True),
        sa.Column("kesesuaian", sa.String(length=40), nullable=True),
        sa.Column("koreksi", sa.Text(), nullable=True),
        sa.Column("masalah_baru", sa.Text(), nullable=True),
        sa.Column("alasan_k", sa.Text(), nullable=True),
        sa.Column("bukti_dapat_diperiksa", sa.Text(), nullable=True),
        sa.Column("hal_belum_jelas", sa.Text(), nullable=True),
        sa.Column("catatan_independensi", sa.Text(), nullable=True),
        sa.Column("catatan_akses", sa.Text(), nullable=True),
        sa.Column("k1", sa.String(length=40), nullable=True),
        sa.Column("k2", sa.String(length=40), nullable=True),
        sa.Column("k3", sa.String(length=40), nullable=True),
        sa.Column("k4", sa.String(length=40), nullable=True),
        sa.Column("indikasi_risiko", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=40), server_default=sa.text("'draf'"), nullable=False),
        sa.Column("menggantikan_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["masalah_id"],
            ["redesain_masalah.id"],
            name=op.f("fk_redesain_konfirmasi_masalah_id_redesain_masalah"),
        ),
        sa.ForeignKeyConstraint(
            ["menggantikan_id"],
            ["redesain_konfirmasi.id"],
            name=op.f("fk_redesain_konfirmasi_menggantikan_id_redesain_konfirmasi"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_konfirmasi")),
    )
    op.create_index(
        op.f("ix_redesain_konfirmasi_masalah_id"),
        "redesain_konfirmasi",
        ["masalah_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_redesain_konfirmasi_kode_orang"),
        "redesain_konfirmasi",
        ["kode_orang"],
        unique=False,
    )
    op.create_index(
        op.f("ix_redesain_konfirmasi_sekolah_id"),
        "redesain_konfirmasi",
        ["sekolah_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_redesain_konfirmasi_sekolah_id"), table_name="redesain_konfirmasi")
    op.drop_index(op.f("ix_redesain_konfirmasi_kode_orang"), table_name="redesain_konfirmasi")
    op.drop_index(op.f("ix_redesain_konfirmasi_masalah_id"), table_name="redesain_konfirmasi")
    op.drop_table("redesain_konfirmasi")
    op.drop_column("redesain_masalah", "eskalasi_pada")
