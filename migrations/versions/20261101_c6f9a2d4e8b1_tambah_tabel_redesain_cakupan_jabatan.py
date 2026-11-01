"""tambah tabel redesain_cakupan_jabatan

Revision ID: c6f9a2d4e8b1
Revises: b5e8f1c3d7a2
Create Date: 2026-11-01 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6f9a2d4e8b1"
down_revision: str | None = "b5e8f1c3d7a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "redesain_cakupan_jabatan",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("role_kode", sa.String(length=10), nullable=False),
        sa.Column("nama_jabatan", sa.String(length=200), nullable=False),
        sa.Column("jabatan_id", sa.String(length=40), nullable=True),
        sa.Column("cabang", sa.String(length=20), nullable=False),
        sa.Column(
            "status_unit", sa.String(length=40), server_default="Belum diperiksa", nullable=False
        ),
        sa.Column(
            "pemegang_diperiksa",
            sa.String(length=40),
            server_default="Belum diperiksa",
            nullable=False,
        ),
        sa.Column(
            "inventori_ditinjau",
            sa.String(length=40),
            server_default="Belum diperiksa",
            nullable=False,
        ),
        sa.Column(
            "peta_diperkuat", sa.String(length=40), server_default="Belum diperiksa", nullable=False
        ),
        sa.Column("gap_variasi", sa.Text(), nullable=True),
        sa.Column("pic_kode_orang", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["jabatan_id"], ["jabatan.id"], name="fk_redesain_cakupan_jabatan_jabatan"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_cakupan_jabatan")),
        sa.UniqueConstraint("role_kode", "cabang", name="uq_redesain_cakupan_jabatan_role_cabang"),
    )
    op.create_index(
        op.f("ix_redesain_cakupan_jabatan_role_kode"),
        "redesain_cakupan_jabatan",
        ["role_kode"],
        unique=False,
    )
    op.create_index(
        op.f("ix_redesain_cakupan_jabatan_jabatan_id"),
        "redesain_cakupan_jabatan",
        ["jabatan_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_redesain_cakupan_jabatan_jabatan_id"), table_name="redesain_cakupan_jabatan"
    )
    op.drop_index(
        op.f("ix_redesain_cakupan_jabatan_role_kode"), table_name="redesain_cakupan_jabatan"
    )
    op.drop_table("redesain_cakupan_jabatan")
