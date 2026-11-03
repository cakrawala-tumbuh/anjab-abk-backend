"""tambah item_bank_hash pada wcp_responden dan dcs_responden

Hash bank item aktif yang berlaku saat responden submit final. Kolom nullable tanpa
backfill: hash bank masa lalu untuk responden lama tidak diketahui.

Revision ID: b3e8f1c5a7d2
Revises: a9c4e7b2d6f1
Create Date: 2026-11-03 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3e8f1c5a7d2"
down_revision: str | None = "a9c4e7b2d6f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("wcp_responden", sa.Column("item_bank_hash", sa.String(length=64), nullable=True))
    op.add_column("dcs_responden", sa.Column("item_bank_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("dcs_responden", "item_bank_hash")
    op.drop_column("wcp_responden", "item_bank_hash")
