"""sasaran usulan batch P02 dan lebar sasaran_id

Menambah tiga nilai `SasaranUsulan` (`JABATAN`, `REDESAIN_MASALAH`, `PROTOKOL_RISET`) pada CHECK
`ck_ai_usulan_sasaran_jenis` dan melebarkan `ai_usulan.sasaran_id` dari 36 ke 40 karakter agar
id `jabatan` (`String(40)`) muat. Ditulis tangan: autogenerate tidak mendeteksi perubahan CHECK.

`downgrade()` mengembalikan keduanya dan GAGAL bila saat itu masih ada baris bernilai sasaran
baru atau `sasaran_id` lebih dari 36 karakter (konvensi downgrade best-effort repo ini).

Revision ID: 12a4ee50e4f3
Revises: cc4cbfe34e90
Create Date: 2026-11-09 03:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "12a4ee50e4f3"
down_revision: str | None = "cc4cbfe34e90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAMA_CK = "ck_ai_usulan_sasaran_jenis"
_LAMA = ("NARASI_KASUS", "NARASI_SUMBER")
_BARU = (*_LAMA, "JABATAN", "REDESAIN_MASALAH", "PROTOKOL_RISET")


def _ekspresi(nilai: tuple[str, ...]) -> str:
    """Ekspresi `sasaran_jenis IN (...)` dari daftar nilai."""
    return "sasaran_jenis IN (" + ", ".join(f"'{n}'" for n in nilai) + ")"


def upgrade() -> None:
    op.drop_constraint(op.f(_NAMA_CK), "ai_usulan", type_="check")
    op.create_check_constraint(op.f(_NAMA_CK), "ai_usulan", _ekspresi(_BARU))
    op.alter_column(
        "ai_usulan",
        "sasaran_id",
        existing_type=sa.String(length=36),
        type_=sa.String(length=40),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "ai_usulan",
        "sasaran_id",
        existing_type=sa.String(length=40),
        type_=sa.String(length=36),
        existing_nullable=False,
    )
    op.drop_constraint(op.f(_NAMA_CK), "ai_usulan", type_="check")
    op.create_check_constraint(op.f(_NAMA_CK), "ai_usulan", _ekspresi(_LAMA))
