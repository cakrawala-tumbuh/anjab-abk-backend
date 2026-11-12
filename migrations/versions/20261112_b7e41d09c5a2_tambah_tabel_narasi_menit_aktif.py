"""tambah tabel narasi_menit_aktif

Revision ID: b7e41d09c5a2
Revises: 6c2d9a41b7e3
Create Date: 2026-11-12 18:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e41d09c5a2"
down_revision: str | None = "6c2d9a41b7e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "narasi_menit_aktif",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("narasi_id", sa.String(length=36), nullable=False),
        sa.Column("actor_key", sa.String(length=254), nullable=False),
        sa.Column("menit", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["narasi_id"],
            ["narasi_kasus.id"],
            name=op.f("fk_narasi_menit_aktif_narasi_id_narasi_kasus"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_narasi_menit_aktif")),
        sa.UniqueConstraint(
            "narasi_id", "actor_key", "menit", name="uq_narasi_menit_aktif_narasi_actor_menit"
        ),
    )
    op.create_index("ix_narasi_menit_aktif_menit", "narasi_menit_aktif", ["menit"], unique=False)
    # Append-only: memakai ulang fungsi `narasi_tolak_ubah()` (revisi 74125eebc244).
    op.execute(
        "CREATE TRIGGER trg_narasi_menit_aktif_append_only "
        "BEFORE UPDATE OR DELETE ON narasi_menit_aktif "
        "FOR EACH ROW EXECUTE FUNCTION narasi_tolak_ubah()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_narasi_menit_aktif_append_only ON narasi_menit_aktif")
    op.drop_index("ix_narasi_menit_aktif_menit", table_name="narasi_menit_aktif")
    op.drop_table("narasi_menit_aktif")
