"""hapus kolom unit dari ti_sesi — sesi TI hanya terikat jabatan, bukan unit/jenjang

Latar belakang
--------------
Sesi Task Inventory semula memiliki kolom `unit` (TK/SD/SMP/SMA) yang membedakan
sesi berdasarkan jenjang pendidikan. Desain ini digantikan: sesi TI cukup terikat pada
jabatan (`jabatan_id`) tanpa perlu unit, konsisten dengan DCS/WCP. Uniqueness constraint
berubah dari `(unit, jabatan_id, periode)` menjadi `(jabatan_id, periode)`.

Downgrade hanya mengembalikan kolom (NULL untuk semua baris), bukan data aslinya.

Revision ID: d3e6f1a8b9c2
Revises: a1c4e7f9b2d6
Create Date: 2026-06-25 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d3e6f1a8b9c2"
down_revision: str | None = "a1c4e7f9b2d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("ti_sesi", "unit")


def downgrade() -> None:
    op.add_column(
        "ti_sesi",
        sa.Column("unit", sa.String(length=20), nullable=True),
    )
