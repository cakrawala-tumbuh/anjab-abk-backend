"""klarifikasi: disposisi DITOLAK dan UNIQUE ai_usulan_id

Revision ID: 6c2d9a41b7e3
Revises: 1e85e065fc4a
Create Date: 2026-11-12 22:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "6c2d9a41b7e3"
down_revision: str | None = "1e85e065fc4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_narasi_klarifikasi_disposition"), "narasi_klarifikasi", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_narasi_klarifikasi_disposition"),
        "narasi_klarifikasi",
        "disposition IN ('TERBUKA', 'TERJAWAB', 'DIBATALKAN', 'DITOLAK')",
    )
    op.create_unique_constraint(
        "uq_narasi_klarifikasi_ai_usulan", "narasi_klarifikasi", ["ai_usulan_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_narasi_klarifikasi_ai_usulan", "narasi_klarifikasi", type_="unique")
    # Baris berdisposisi DITOLAK dikembalikan ke bentuk lama: ditolak tapi masih TERBUKA.
    op.execute(
        "UPDATE narasi_klarifikasi SET disposition = 'TERBUKA' WHERE disposition = 'DITOLAK'"
    )
    op.drop_constraint(
        op.f("ck_narasi_klarifikasi_disposition"), "narasi_klarifikasi", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_narasi_klarifikasi_disposition"),
        "narasi_klarifikasi",
        "disposition IN ('TERBUKA', 'TERJAWAB', 'DIBATALKAN')",
    )
