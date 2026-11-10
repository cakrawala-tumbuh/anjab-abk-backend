"""redesain_konteks asal usulan AI

Menambah penanda asal `ai_usulan_id` (FK `ai_usulan.id`, `ON DELETE RESTRICT`) dan
`ai_kandidat_indeks` pada `redesain_konteks` (backlog `#128`, aksi Terapkan kandidat P11).
CHECK `ck_redesain_konteks_asal_usulan_ai` menuntut keduanya null atau keduanya terisi;
UNIQUE `uq_redesain_konteks_ai_usulan_kandidat` menjamin satu kandidat diterapkan tepat
sekali. Baris yang ada (seed K-01...K-14, konteks manual) tetap null di kedua kolom.

Revision ID: 8e8950b14821
Revises: b7d3e5a91c48
Create Date: 2026-11-10 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8e8950b14821"
down_revision: str | None = "b7d3e5a91c48"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABEL = "redesain_konteks"


def upgrade() -> None:
    """Tambah dua kolom penanda asal beserta FK, CHECK, dan UNIQUE-nya."""
    op.add_column(_TABEL, sa.Column("ai_usulan_id", sa.String(length=36), nullable=True))
    op.add_column(_TABEL, sa.Column("ai_kandidat_indeks", sa.SmallInteger(), nullable=True))
    op.create_foreign_key(
        op.f("fk_redesain_konteks_ai_usulan_id_ai_usulan"),
        _TABEL,
        "ai_usulan",
        ["ai_usulan_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_redesain_konteks_asal_usulan_ai"),
        _TABEL,
        "(ai_usulan_id IS NULL) = (ai_kandidat_indeks IS NULL)",
    )
    op.create_unique_constraint(
        "uq_redesain_konteks_ai_usulan_kandidat",
        _TABEL,
        ["ai_usulan_id", "ai_kandidat_indeks"],
    )


def downgrade() -> None:
    """Buang UNIQUE, CHECK, FK, lalu kedua kolom (penanda asal hilang)."""
    op.drop_constraint("uq_redesain_konteks_ai_usulan_kandidat", _TABEL, type_="unique")
    op.drop_constraint(op.f("ck_redesain_konteks_asal_usulan_ai"), _TABEL, type_="check")
    op.drop_constraint(
        op.f("fk_redesain_konteks_ai_usulan_id_ai_usulan"), _TABEL, type_="foreignkey"
    )
    op.drop_column(_TABEL, "ai_kandidat_indeks")
    op.drop_column(_TABEL, "ai_usulan_id")
