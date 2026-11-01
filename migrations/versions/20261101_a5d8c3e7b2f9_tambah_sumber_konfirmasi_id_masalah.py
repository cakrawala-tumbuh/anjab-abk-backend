"""tambah kolom redesain_masalah.sumber_konfirmasi_id

Revision ID: a5d8c3e7b2f9
Revises: f4c7d2a9b6e1
Create Date: 2026-11-01 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a5d8c3e7b2f9"
down_revision: str | None = "f4c7d2a9b6e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "redesain_masalah",
        sa.Column("sumber_konfirmasi_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_redesain_masalah_sumber_konfirmasi",
        "redesain_masalah",
        "redesain_konfirmasi",
        ["sumber_konfirmasi_id"],
        ["id"],
    )
    op.create_index(
        op.f("ix_redesain_masalah_sumber_konfirmasi_id"),
        "redesain_masalah",
        ["sumber_konfirmasi_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_redesain_masalah_sumber_konfirmasi_id"), table_name="redesain_masalah")
    op.drop_constraint(
        "fk_redesain_masalah_sumber_konfirmasi", "redesain_masalah", type_="foreignkey"
    )
    op.drop_column("redesain_masalah", "sumber_konfirmasi_id")
