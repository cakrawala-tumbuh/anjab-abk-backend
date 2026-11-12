"""tambah tabel register klarifikasi narasi

Revision ID: 1e85e065fc4a
Revises: f02ed2fece58
Create Date: 2026-11-12 13:23:55.035442
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "1e85e065fc4a"
down_revision: str | None = "f02ed2fece58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "narasi_klarifikasi",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("narasi_id", sa.String(length=36), nullable=False),
        sa.Column("claim_id", sa.String(length=100), nullable=False),
        sa.Column("source_ids_checked", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("materiality_reason", sa.Text(), nullable=False),
        sa.Column("alternative_hypothesis", sa.Text(), nullable=False),
        sa.Column("intended_decision", sa.Text(), nullable=False),
        sa.Column("recipient_role", sa.String(length=100), nullable=False),
        sa.Column("periode", sa.String(length=20), nullable=False),
        sa.Column("exposure", sa.String(length=30), nullable=False),
        sa.Column("due_trigger", sa.Text(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column(
            "reviewer_approval",
            sa.String(length=20),
            server_default=sa.text("'MENUNGGU'"),
            nullable=False,
        ),
        sa.Column("response_ref", sa.String(length=200), nullable=True),
        sa.Column("jawaban_mentah", sa.Text(), nullable=True),
        sa.Column(
            "disposition", sa.String(length=20), server_default=sa.text("'TERBUKA'"), nullable=False
        ),
        sa.Column("ai_usulan_id", sa.String(length=36), nullable=True),
        sa.Column("dibuat_oleh", sa.String(length=254), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "disposition IN ('TERBUKA', 'TERJAWAB', 'DIBATALKAN')",
            name=op.f("ck_narasi_klarifikasi_disposition"),
        ),
        sa.CheckConstraint(
            "exposure IN ('TIDAK_BERLAKU', 'BELUM_TERPAPAR', 'LOCKED_PRE_EXPOSURE', "
            "'EXPOSED', 'TIDAK_DIKETAHUI')",
            name=op.f("ck_narasi_klarifikasi_exposure"),
        ),
        sa.CheckConstraint(
            "reviewer_approval IN ('MENUNGGU', 'DISETUJUI', 'DITOLAK')",
            name=op.f("ck_narasi_klarifikasi_reviewer_approval"),
        ),
        sa.ForeignKeyConstraint(
            ["ai_usulan_id"],
            ["ai_usulan.id"],
            name=op.f("fk_narasi_klarifikasi_ai_usulan_id_ai_usulan"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["narasi_id"],
            ["narasi_kasus.id"],
            name=op.f("fk_narasi_klarifikasi_narasi_id_narasi_kasus"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_narasi_klarifikasi")),
    )
    op.create_index(
        op.f("ix_narasi_klarifikasi_narasi_id"), "narasi_klarifikasi", ["narasi_id"], unique=False
    )
    op.create_index(
        "uq_narasi_klarifikasi_terbuka",
        "narasi_klarifikasi",
        ["narasi_id", "claim_id"],
        unique=True,
        postgresql_where=sa.text("disposition = 'TERBUKA'"),
    )
    op.create_table(
        "narasi_klarifikasi_event",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("klarifikasi_id", sa.String(length=36), nullable=False),
        sa.Column("aksi", sa.String(length=20), nullable=False),
        sa.Column("actor_key", sa.String(length=254), nullable=False),
        sa.Column("catatan", sa.Text(), nullable=True),
        sa.Column(
            "terjadi_pada",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "aksi IN ('DIBUAT', 'DISETUJUI', 'DITOLAK', 'JAWABAN_DICATAT', 'DIBATALKAN')",
            name=op.f("ck_narasi_klarifikasi_event_aksi"),
        ),
        sa.ForeignKeyConstraint(
            ["klarifikasi_id"],
            ["narasi_klarifikasi.id"],
            name=op.f("fk_narasi_klarifikasi_event_klarifikasi_id_narasi_klarifikasi"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_narasi_klarifikasi_event")),
    )
    op.create_index(
        op.f("ix_narasi_klarifikasi_event_klarifikasi_id"),
        "narasi_klarifikasi_event",
        ["klarifikasi_id"],
        unique=False,
    )
    # Riwayat append-only: memakai ulang fungsi `narasi_tolak_ubah()` (revisi 74125eebc244).
    op.execute(
        "CREATE TRIGGER trg_narasi_klarifikasi_event_append_only "
        "BEFORE UPDATE OR DELETE ON narasi_klarifikasi_event "
        "FOR EACH ROW EXECUTE FUNCTION narasi_tolak_ubah()"
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS trg_narasi_klarifikasi_event_append_only "
        "ON narasi_klarifikasi_event"
    )
    op.drop_index(
        op.f("ix_narasi_klarifikasi_event_klarifikasi_id"), table_name="narasi_klarifikasi_event"
    )
    op.drop_table("narasi_klarifikasi_event")
    op.drop_index(
        "uq_narasi_klarifikasi_terbuka",
        table_name="narasi_klarifikasi",
        postgresql_where=sa.text("disposition = 'TERBUKA'"),
    )
    op.drop_index(op.f("ix_narasi_klarifikasi_narasi_id"), table_name="narasi_klarifikasi")
    op.drop_table("narasi_klarifikasi")
    # ### end Alembic commands ###
