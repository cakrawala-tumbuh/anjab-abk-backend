"""tambah tabel riset_protokol_signoff

Bukti sign-off PI/etik per protokol riset terkunci (backlog `#139`, OD-09). Satu baris per
protokol (UNIQUE `protokol_id`), PDF persetujuan etik disimpan sebagai `bytea`. FK ke
`riset_protokol.id` `ON DELETE RESTRICT`. `downgrade()` membuang tabel beserta isinya.

Revision ID: d41f8a6e2b70
Revises: b7e41d09c5a2
Create Date: 2026-11-12 19:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d41f8a6e2b70"
down_revision: str | None = "b7e41d09c5a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "riset_protokol_signoff",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("protokol_id", sa.String(length=36), nullable=False),
        sa.Column("pi_nama", sa.String(length=200), nullable=False),
        sa.Column("tanggal_persetujuan_etik", sa.Date(), nullable=False),
        sa.Column("nomor_persetujuan_etik", sa.String(length=100), nullable=True),
        sa.Column("lampiran_pdf", sa.LargeBinary(), nullable=False),
        sa.Column("lampiran_nama", sa.String(length=255), nullable=False),
        sa.Column("lampiran_ukuran", sa.Integer(), nullable=False),
        sa.Column("lampiran_sha256", sa.String(length=64), nullable=False),
        sa.Column("dicatat_oleh", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["protokol_id"],
            ["riset_protokol.id"],
            name=op.f("fk_riset_protokol_signoff_protokol_id_riset_protokol"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_riset_protokol_signoff")),
        sa.UniqueConstraint("protokol_id", name="uq_riset_protokol_signoff_protokol"),
    )


def downgrade() -> None:
    op.drop_table("riset_protokol_signoff")
