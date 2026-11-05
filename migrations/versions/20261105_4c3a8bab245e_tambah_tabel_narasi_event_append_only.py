"""tambah tabel narasi event append only

Revision ID: 4c3a8bab245e
Revises: 74125eebc244
Create Date: 2026-11-05 05:56:35.526917
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4c3a8bab245e"
down_revision: str | None = "74125eebc244"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "narasi_event",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("narasi_id", sa.String(length=36), nullable=False),
        sa.Column("narasi_versi_id", sa.String(length=36), nullable=True),
        sa.Column("actor_key", sa.String(length=254), nullable=False),
        sa.Column("actor_role", sa.String(length=40), nullable=False),
        sa.Column("event_kind", sa.String(length=30), nullable=False),
        sa.Column("dari_status", sa.String(length=30), nullable=False),
        sa.Column("ke_status", sa.String(length=30), nullable=False),
        sa.Column("event_notes", sa.Text(), nullable=True),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "dari_status IN ('SOURCE_CHECKED', 'AI_DRAFT', 'NEED_FACT', 'TEAM_REVIEW', "
            "'TEAM_VERIFIED', 'SUBJECT_REVIEW', 'SUBJECT_CONFIRMED', 'SUBJECT_CORRECTION', "
            "'SUBJECT_REJECTED', 'SUBJECT_UNCERTAIN', 'FINAL_TEAM_REVIEW', 'RELEASED_FACT', "
            "'RELEASED_LIMITED', 'RETURN_FOR_CLARIFICATION')",
            name=op.f("ck_narasi_event_dari_status"),
        ),
        sa.CheckConstraint(
            "event_kind IN ('TEAM_APPROVE', 'TEAM_REVISE', 'TEAM_REJECT', 'NEED_SOURCE', "
            "'SUBJECT_CONFIRM', 'SUBJECT_CORRECT', 'SUBJECT_REJECT', 'SUBJECT_UNSURE', "
            "'FINAL_TEAM_APPROVE', 'RELEASE_LIMITED', 'RETURN_CLARIFICATION')",
            name=op.f("ck_narasi_event_event_kind"),
        ),
        sa.CheckConstraint(
            "ke_status IN ('SOURCE_CHECKED', 'AI_DRAFT', 'NEED_FACT', 'TEAM_REVIEW', "
            "'TEAM_VERIFIED', 'SUBJECT_REVIEW', 'SUBJECT_CONFIRMED', 'SUBJECT_CORRECTION', "
            "'SUBJECT_REJECTED', 'SUBJECT_UNCERTAIN', 'FINAL_TEAM_REVIEW', 'RELEASED_FACT', "
            "'RELEASED_LIMITED', 'RETURN_FOR_CLARIFICATION')",
            name=op.f("ck_narasi_event_ke_status"),
        ),
        sa.ForeignKeyConstraint(
            ["narasi_id"], ["narasi_kasus.id"], name="fk_narasi_event_narasi_id_narasi_kasus"
        ),
        sa.ForeignKeyConstraint(
            ["narasi_versi_id"],
            ["narasi_versi.id"],
            name="fk_narasi_event_narasi_versi_id_narasi_versi",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_narasi_event")),
    )
    op.create_index(
        "ix_narasi_event_narasi_id_event_at",
        "narasi_event",
        ["narasi_id", "event_at"],
        unique=False,
    )
    # Append-only ditegakkan basis data; fungsi `narasi_tolak_ubah()` dibuat revisi 74125eebc244.
    op.execute(
        "CREATE TRIGGER trg_narasi_event_append_only BEFORE UPDATE OR DELETE ON narasi_event "
        "FOR EACH ROW EXECUTE FUNCTION narasi_tolak_ubah()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_narasi_event_append_only ON narasi_event")
    op.drop_index("ix_narasi_event_narasi_id_event_at", table_name="narasi_event")
    op.drop_table("narasi_event")
