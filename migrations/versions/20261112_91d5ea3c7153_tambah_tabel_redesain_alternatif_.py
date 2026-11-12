"""tambah tabel redesain_alternatif_penerima dan redesain_kesiapan

Penerima jamak per alternatif (+ backfill dari `pihak_penerima_jabatan_id`) dan kesiapan
append-only per penerima per periode (backlog `#133`).

Revision ID: 91d5ea3c7153
Revises: a1c5e7b93d20
Create Date: 2026-11-12 09:52:51.858814
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "91d5ea3c7153"
down_revision: str | None = "a1c5e7b93d20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "redesain_alternatif_penerima",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("alternatif_id", sa.String(length=36), nullable=False),
        sa.Column("penerima_jabatan_id", sa.String(length=40), nullable=False),
        sa.Column("material", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("catatan", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["alternatif_id"],
            ["redesain_alternatif.id"],
            name=op.f("fk_redesain_alternatif_penerima_alternatif_id_redesain_alternatif"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["penerima_jabatan_id"],
            ["jabatan.id"],
            name=op.f("fk_redesain_alternatif_penerima_penerima_jabatan_id_jabatan"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_alternatif_penerima")),
        sa.UniqueConstraint(
            "alternatif_id", "penerima_jabatan_id", name="uq_redesain_alternatif_penerima_jabatan"
        ),
    )
    op.create_index(
        op.f("ix_redesain_alternatif_penerima_alternatif_id"),
        "redesain_alternatif_penerima",
        ["alternatif_id"],
        unique=False,
    )
    # Backfill: satu baris penerima (material) per alternatif yang kolom lamanya terisi.
    op.execute(
        sa.text(
            "INSERT INTO redesain_alternatif_penerima "
            "(id, alternatif_id, penerima_jabatan_id, material, catatan, created_at) "
            "SELECT gen_random_uuid()::text, id, pihak_penerima_jabatan_id, true, NULL, "
            "created_at FROM redesain_alternatif WHERE pihak_penerima_jabatan_id IS NOT NULL"
        )
    )
    op.create_table(
        "redesain_kesiapan",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("penerima_id", sa.String(length=36), nullable=False),
        sa.Column("periode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("delta_asal_jam", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("delta_asal_estimasi", sa.String(length=20), nullable=False),
        sa.Column("delta_penerima_jam", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("delta_penerima_estimasi", sa.String(length=20), nullable=False),
        sa.Column("delta_organisasi_jam", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("delta_organisasi_estimasi", sa.String(length=20), nullable=False),
        sa.Column("syarat", sa.Text(), nullable=True),
        sa.Column("alasan_hold", sa.Text(), nullable=True),
        sa.Column("dinilai_oleh", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(delta_asal_estimasi = 'NOT_ESTIMABLE') = (delta_asal_jam IS NULL)",
            name=op.f("ck_redesain_kesiapan_delta_asal_konsisten"),
        ),
        sa.CheckConstraint(
            "(delta_organisasi_estimasi = 'NOT_ESTIMABLE') = (delta_organisasi_jam IS NULL)",
            name=op.f("ck_redesain_kesiapan_delta_organisasi_konsisten"),
        ),
        sa.CheckConstraint(
            "(delta_penerima_estimasi = 'NOT_ESTIMABLE') = (delta_penerima_jam IS NULL)",
            name=op.f("ck_redesain_kesiapan_delta_penerima_konsisten"),
        ),
        sa.CheckConstraint(
            "delta_asal_estimasi IN ('ESTIMATED', 'NOT_ESTIMABLE')",
            name=op.f("ck_redesain_kesiapan_delta_asal_estimasi"),
        ),
        sa.CheckConstraint(
            "delta_organisasi_estimasi IN ('ESTIMATED', 'NOT_ESTIMABLE')",
            name=op.f("ck_redesain_kesiapan_delta_organisasi_estimasi"),
        ),
        sa.CheckConstraint(
            "delta_penerima_estimasi IN ('ESTIMATED', 'NOT_ESTIMABLE')",
            name=op.f("ck_redesain_kesiapan_delta_penerima_estimasi"),
        ),
        sa.CheckConstraint(
            "status IN ('READY', 'CONDITIONAL', 'HOLD')", name=op.f("ck_redesain_kesiapan_status")
        ),
        sa.ForeignKeyConstraint(
            ["penerima_id"],
            ["redesain_alternatif_penerima.id"],
            name=op.f("fk_redesain_kesiapan_penerima_id_redesain_alternatif_penerima"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redesain_kesiapan")),
    )
    op.create_index(
        op.f("ix_redesain_kesiapan_penerima_id"), "redesain_kesiapan", ["penerima_id"], unique=False
    )


def downgrade() -> None:
    """Buang kedua tabel beserta isinya (kolom lama tidak disentuh sehingga data asal utuh)."""
    op.drop_index(op.f("ix_redesain_kesiapan_penerima_id"), table_name="redesain_kesiapan")
    op.drop_table("redesain_kesiapan")
    op.drop_index(
        op.f("ix_redesain_alternatif_penerima_alternatif_id"),
        table_name="redesain_alternatif_penerima",
    )
    op.drop_table("redesain_alternatif_penerima")
