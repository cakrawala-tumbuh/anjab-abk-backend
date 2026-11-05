"""tambah tabel narasi kasus versi dan sumber

Revision ID: 74125eebc244
Revises: 5a0f1cc6d400
Create Date: 2026-11-05 04:31:37.777216
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "74125eebc244"
down_revision: str | None = "5a0f1cc6d400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "narasi_kasus",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("instrument_id", sa.String(length=50), nullable=False),
        sa.Column("field_key", sa.String(length=100), nullable=False),
        sa.Column("peran_ref", sa.String(length=100), nullable=False),
        sa.Column("periode", sa.String(length=20), nullable=False),
        sa.Column("sekolah_id", sa.String(length=40), nullable=True),
        sa.Column("assignment_ref", sa.String(length=100), nullable=True),
        sa.Column("target_subject_ref", sa.String(length=100), nullable=True),
        sa.Column("konteks_kode", sa.String(length=100), nullable=True),
        sa.Column("narrative_kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("intended_use", sa.String(length=200), nullable=False),
        sa.Column("permission_scope", sa.String(length=200), nullable=False),
        sa.Column("sensitivity_class", sa.String(length=40), nullable=False),
        sa.Column("dibuat_oleh", sa.String(length=254), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "narrative_kind IN ('F1_FORMAL', 'F2_ACTUAL', 'F3_HANDOFF', "
            "'F4_ANALYTICAL', 'F5_RESEARCH')",
            name=op.f("ck_narasi_kasus_narrative_kind"),
        ),
        sa.CheckConstraint(
            "status IN ('SOURCE_CHECKED', 'AI_DRAFT', 'NEED_FACT', 'TEAM_REVIEW', "
            "'TEAM_VERIFIED', 'SUBJECT_REVIEW', 'SUBJECT_CONFIRMED', 'SUBJECT_CORRECTION', "
            "'SUBJECT_REJECTED', 'SUBJECT_UNCERTAIN', 'FINAL_TEAM_REVIEW', 'RELEASED_FACT', "
            "'RELEASED_LIMITED', 'RETURN_FOR_CLARIFICATION')",
            name=op.f("ck_narasi_kasus_status"),
        ),
        sa.ForeignKeyConstraint(
            ["sekolah_id"], ["sekolah.id"], name="fk_narasi_kasus_sekolah_id_sekolah"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_narasi_kasus")),
        sa.UniqueConstraint(
            "instrument_id",
            "field_key",
            "peran_ref",
            "periode",
            "sekolah_id",
            "assignment_ref",
            "target_subject_ref",
            "konteks_kode",
            name="uq_narasi_kasus_lingkup",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(
        "ix_narasi_kasus_status_updated_at", "narasi_kasus", ["status", "updated_at"], unique=False
    )
    op.create_table(
        "narasi_versi",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("narasi_id", sa.String(length=36), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("revision_origin", sa.String(length=20), nullable=False),
        sa.Column("status_hasil", sa.String(length=30), nullable=False),
        sa.Column("teks", sa.Text(), nullable=True),
        sa.Column("supersedes_id", sa.String(length=36), nullable=True),
        sa.Column("ai_run_id", sa.String(length=36), nullable=True),
        sa.Column("output_hash", sa.String(length=64), nullable=True),
        sa.Column("metadata_ai", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("dibuat_oleh", sa.String(length=254), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "revision_origin IN ('AI_DRAFT', 'HUMAN_CORRECTION', 'AI_REVISION', "
            "'REVIEWER_EDIT', 'ORIGINAL_QUOTE')",
            name=op.f("ck_narasi_versi_revision_origin"),
        ),
        sa.CheckConstraint("revision_no > 0", name=op.f("ck_narasi_versi_revision_no_positif")),
        sa.ForeignKeyConstraint(
            ["ai_run_id"], ["ai_run.id"], name="fk_narasi_versi_ai_run_id_ai_run"
        ),
        sa.ForeignKeyConstraint(
            ["narasi_id"], ["narasi_kasus.id"], name="fk_narasi_versi_narasi_id_narasi_kasus"
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["narasi_versi.id"],
            name="fk_narasi_versi_supersedes_id_narasi_versi",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_narasi_versi")),
        sa.UniqueConstraint("ai_run_id", name=op.f("uq_narasi_versi_ai_run_id")),
        sa.UniqueConstraint("narasi_id", "revision_no", name="uq_narasi_versi_narasi_revisi"),
    )
    op.create_table(
        "narasi_versi_sumber",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("narasi_versi_id", sa.String(length=36), nullable=False),
        sa.Column("sumber_id", sa.String(length=36), nullable=False),
        sa.Column("source_span", sa.Text(), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("basis_relation", sa.String(length=20), nullable=False),
        sa.CheckConstraint(
            "basis_relation IN ('DIRECT', 'CONTEXT', 'CONTRADICTS', 'UNKNOWN')",
            name=op.f("ck_narasi_versi_sumber_basis_relation"),
        ),
        sa.ForeignKeyConstraint(
            ["narasi_versi_id"],
            ["narasi_versi.id"],
            name="fk_narasi_versi_sumber_narasi_versi_id_narasi_versi",
        ),
        sa.ForeignKeyConstraint(
            ["sumber_id"],
            ["narasi_sumber.id"],
            name="fk_narasi_versi_sumber_sumber_id_narasi_sumber",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_narasi_versi_sumber")),
    )
    op.create_index(
        "ix_narasi_versi_sumber_narasi_versi_id",
        "narasi_versi_sumber",
        ["narasi_versi_id"],
        unique=False,
    )
    # Append-only ditegakkan basis data (bukan hanya service): UPDATE/DELETE ditolak.
    op.execute(
        """
        CREATE FUNCTION narasi_tolak_ubah() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'tabel % bersifat append-only: % ditolak', TG_TABLE_NAME, TG_OP
                USING ERRCODE = 'restrict_violation';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for tabel in ("narasi_versi", "narasi_versi_sumber"):
        op.execute(
            f"CREATE TRIGGER trg_{tabel}_append_only BEFORE UPDATE OR DELETE ON {tabel} "
            "FOR EACH ROW EXECUTE FUNCTION narasi_tolak_ubah()"
        )


def downgrade() -> None:
    for tabel in ("narasi_versi_sumber", "narasi_versi"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tabel}_append_only ON {tabel}")
    op.execute("DROP FUNCTION IF EXISTS narasi_tolak_ubah()")
    op.drop_index("ix_narasi_versi_sumber_narasi_versi_id", table_name="narasi_versi_sumber")
    op.drop_table("narasi_versi_sumber")
    op.drop_table("narasi_versi")
    op.drop_index("ix_narasi_kasus_status_updated_at", table_name="narasi_kasus")
    op.drop_table("narasi_kasus")
