"""backfill partisipan.authentik_user_id ke subject email + lebarkan kolom

Latar belakang
--------------
Provider OAuth2 ANJAB-ABK (web & backend) memakai `sub_mode = user_email`, sehingga
klaim `sub` token = email. Backend mencocokkan `partisipan.authentik_user_id == sub`
saat login (`PartisipanService.get_by_subject`). Sebagian data lama mengisi kolom ini
dengan nilai placeholder (`placeholder_xxxxxxxx`) atau pk numerik Authentik — keduanya
tidak pernah sama dengan `sub`, sehingga tautan identitas hanya tertolong fallback email.

Revisi ini:
1. Melebarkan `authentik_user_id` dari VARCHAR(64) → VARCHAR(254) agar muat email
   (lebar email = 254) tanpa terpotong.
2. Mem-backfill `authentik_user_id = email` untuk semua baris yang nilainya belum sama
   dengan email — sehingga pencocokan primer (`authentik_user_id == sub`) langsung tepat.

Backfill bersifat idempoten (no-op pada baris yang sudah benar) dan tidak dapat dipulihkan
(nilai placeholder/pk lama tidak disimpan); downgrade hanya mengembalikan lebar kolom.

Revision ID: a1c4e7f9b2d6
Revises: b2bbd3afbe65
Create Date: 2026-06-25 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c4e7f9b2d6"
down_revision: str | None = "b2bbd3afbe65"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "partisipan",
        "authentik_user_id",
        existing_type=sa.String(length=64),
        type_=sa.String(length=254),
        existing_nullable=True,
    )
    # Selaraskan tautan identitas dengan `sub_mode=user_email`: sub = email.
    op.execute(
        "UPDATE partisipan SET authentik_user_id = email "
        "WHERE authentik_user_id IS DISTINCT FROM email"
    )


def downgrade() -> None:
    # Backfill tidak dipulihkan (nilai lama tidak disimpan); hanya kembalikan lebar kolom.
    op.alter_column(
        "partisipan",
        "authentik_user_id",
        existing_type=sa.String(length=254),
        type_=sa.String(length=64),
        existing_nullable=True,
    )
