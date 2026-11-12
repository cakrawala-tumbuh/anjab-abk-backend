"""tambah tabel ti_cerita_prabank dan ti_paparan_event

Cerita bebas pra-bank per responden Task Inventory (UNIQUE per responden) dan log paparan
bank tugas yang append-only (backlog `#131`). Trigger `BEFORE UPDATE` pada
`ti_paparan_event` memakai ulang fungsi `narasi_tolak_ubah()` dari revisi 74125eebc244;
DELETE tidak ditolak agar `ON DELETE CASCADE` (hapus-paksa sesi) tetap berjalan.

Revision ID: a1c5e7b93d20
Revises: 8e8950b14821
Create Date: 2026-11-12 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c5e7b93d20"
down_revision: str | None = "8e8950b14821"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ti_cerita_prabank",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("responden_id", sa.String(length=40), nullable=False),
        sa.Column("teks", sa.Text(), nullable=False),
        sa.Column("teks_hash", sa.String(length=64), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["responden_id"],
            ["ti_responden.id"],
            name=op.f("fk_ti_cerita_prabank_responden_id_ti_responden"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ti_cerita_prabank")),
        sa.UniqueConstraint("responden_id", name=op.f("uq_ti_cerita_prabank_responden_id")),
    )
    op.create_table(
        "ti_paparan_event",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("responden_id", sa.String(length=40), nullable=False),
        sa.Column("jenis", sa.String(length=20), nullable=False),
        sa.Column(
            "terjadi_pada",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("status_saat_paparan", sa.String(length=25), nullable=False),
        sa.CheckConstraint(
            "jenis IN ('BANK_TUGAS', 'CONTOH_TUGAS')", name=op.f("ck_ti_paparan_event_jenis")
        ),
        sa.CheckConstraint(
            "status_saat_paparan IN ('LOCKED_PRE_EXPOSURE', 'EXPOSED')",
            name=op.f("ck_ti_paparan_event_status_saat_paparan"),
        ),
        sa.ForeignKeyConstraint(
            ["responden_id"],
            ["ti_responden.id"],
            name=op.f("fk_ti_paparan_event_responden_id_ti_responden"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ti_paparan_event")),
    )
    op.create_index(op.f("ix_ti_paparan_event_responden_id"), "ti_paparan_event", ["responden_id"])
    op.execute(
        "CREATE TRIGGER trg_ti_paparan_event_no_update BEFORE UPDATE ON ti_paparan_event "
        "FOR EACH ROW EXECUTE FUNCTION narasi_tolak_ubah()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_ti_paparan_event_no_update ON ti_paparan_event")
    op.drop_index(op.f("ix_ti_paparan_event_responden_id"), table_name="ti_paparan_event")
    op.drop_table("ti_paparan_event")
    op.drop_table("ti_cerita_prabank")
