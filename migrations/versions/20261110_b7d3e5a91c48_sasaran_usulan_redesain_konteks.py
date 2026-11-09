"""sasaran usulan REDESAIN_KONTEKS

Menambah nilai `SasaranUsulan.REDESAIN_KONTEKS` (fungsi P11 Pengusul Konteks) pada CHECK
`ck_ai_usulan_sasaran_jenis`. Ditulis tangan: autogenerate tidak mendeteksi perubahan CHECK.

`downgrade()` mengembalikan CHECK sebelumnya dan GAGAL bila saat itu masih ada baris
`REDESAIN_KONTEKS` (data tidak dihapus diam-diam; konvensi downgrade best-effort repo ini).

Revision ID: b7d3e5a91c48
Revises: e4a7c19b2d63
Create Date: 2026-11-10 09:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "b7d3e5a91c48"
down_revision: str | None = "e4a7c19b2d63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAMA_CK = "ck_ai_usulan_sasaran_jenis"
_LAMA = ("NARASI_KASUS", "NARASI_SUMBER", "JABATAN", "REDESAIN_MASALAH", "PROTOKOL_RISET")
_BARU = (*_LAMA, "REDESAIN_KONTEKS")


def _ekspresi(nilai: tuple[str, ...]) -> str:
    """Ekspresi `sasaran_jenis IN (...)` dari daftar nilai."""
    return "sasaran_jenis IN (" + ", ".join(f"'{n}'" for n in nilai) + ")"


def upgrade() -> None:
    """Perluas CHECK `ck_ai_usulan_sasaran_jenis` dengan `REDESAIN_KONTEKS`."""
    op.drop_constraint(op.f(_NAMA_CK), "ai_usulan", type_="check")
    op.create_check_constraint(op.f(_NAMA_CK), "ai_usulan", _ekspresi(_BARU))


def downgrade() -> None:
    """Pulihkan CHECK tanpa `REDESAIN_KONTEKS`; gagal bila sudah ada baris bernilai itu."""
    op.drop_constraint(op.f(_NAMA_CK), "ai_usulan", type_="check")
    op.create_check_constraint(op.f(_NAMA_CK), "ai_usulan", _ekspresi(_LAMA))
