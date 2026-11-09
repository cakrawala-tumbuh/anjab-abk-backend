"""tambah kolom konteks_server pada ai_usulan

Cuplikan konteks yang diisi server saat pengajuan, bukan oleh model (backlog `#125`). P07
menyimpan `{"authorization_state": ...}` di sini; fungsi lain membiarkannya `NULL`. Tanpa
migrasi data: baris lama tetap `NULL`. `downgrade()` membuang kolom beserta isinya.

Revision ID: e4a7c19b2d63
Revises: ca3b9bb3b458
Create Date: 2026-11-09 18:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e4a7c19b2d63"
down_revision: str | None = "ca3b9bb3b458"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "ai_usulan",
        sa.Column("konteks_server", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ai_usulan", "konteks_server")
