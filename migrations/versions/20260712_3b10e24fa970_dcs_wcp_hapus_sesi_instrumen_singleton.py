"""dcs wcp hapus sesi instrumen singleton

Revision ID: 3b10e24fa970
Revises: 1be8921ba27b
Create Date: 2026-07-12 15:03:37.813260

DCS dan WCP tidak lagi memakai sesi. Tiap instrumen menjadi SINGLETON — satu baris
tetap (`id='dcs'` / `id='wcp'`) di tabel `dcs_instrumen`/`wcp_instrumen` — dengan
penugasan responden langsung (`dcs_responden`/`wcp_responden` kehilangan `sesi_id`,
`partisipan_id` menjadi unik). Meniru pola yang sudah dipakai Time Study
(`ts_penugasan`, lihat revisi `0a58616358f4`). Kolom `periode`/`max_responden`
dihapus — redundan karena 1 deployment = 1 studi. TI dan OPM (sesi jabatan) TIDAK
disentuh oleh revisi ini.

Guard (WAJIB dibaca sebelum dijalankan di produksi): bila ditemukan >1 sesi DCS
(atau WCP) yang MASING-MASING punya minimal 1 responden, `upgrade()` menolak
jalan (`RuntimeError`, pesan menyebut `sesi_id` yang bermasalah) — instrumen
singleton tidak dapat mewakili lebih dari satu "kumpulan responden". Konsolidasikan
responden ke satu sesi dulu sebelum migrasi ini dijalankan.

Backfill data lama (bila ada tepat satu sesi ber-responden):
`min_responden`/`catatan` disalin dari sesi tersebut; status dipetakan
`DRAFT|OPEN -> OPEN`, `CLOSED -> CLOSED`, `ANALYZED -> ANALYZED`. Bila TIDAK ADA
sesi yang punya responden (termasuk database yang baru diinisialisasi), baris
instrumen dibuat dengan default (`status=OPEN`, `min_responden=6`,
`catatan=NULL`) — instrumen sudah OPEN sejak migrasi, admin tidak perlu
melakukan apa pun.

Downgrade dari revisi ini best-effort (mengikuti konvensi `0a58616358f4`):
struktur tabel lama (`dcs_sesi`/`wcp_sesi`, kolom `sesi_id`) dipulihkan KOSONG —
data instrumen singleton & tautan sesi-responden yang sudah hilang saat upgrade
TIDAK direkonstruksi. Kolom `sesi_id` yang dipulihkan sengaja `nullable=True`
(berbeda dari skema asli yang `NOT NULL`) karena nilainya tidak diketahui.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3b10e24fa970"
down_revision: str | None = "1be8921ba27b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _seed_instrumen(
    connection: sa.engine.Connection,
    *,
    modul: str,
    sesi_table: str,
    responden_table: str,
    instrumen_table: str,
    instrumen_id: str,
) -> None:
    """Guard (>1 sesi ber-responden) lalu sisipkan satu baris instrumen singleton.

    `min_responden`/`catatan`/`status` disalin dari sesi ber-responden bila ADA
    (dan hanya boleh ada SATU); jika tidak ada, baris instrumen dibuat dengan
    default (status OPEN, min_responden 6, catatan NULL).
    """
    groups = connection.execute(
        sa.text(f"SELECT sesi_id, count(*) AS n FROM {responden_table} GROUP BY sesi_id")
    ).all()
    if len(groups) > 1:
        sesi_ids = ", ".join(str(g.sesi_id) for g in groups)
        raise RuntimeError(
            f"Migrasi {modul} dibatalkan: ditemukan >1 sesi {modul} yang masing-masing "
            f"memiliki responden ({sesi_ids}). Instrumen singleton tidak dapat mewakili "
            "lebih dari satu kumpulan responden — konsolidasikan responden ke satu sesi "
            "(pindahkan/hapus responden dari sesi lain) sebelum menjalankan migrasi ini."
        )

    status = "OPEN"
    min_responden = 6
    catatan = None
    if groups:
        source_sesi_id = groups[0].sesi_id
        row = connection.execute(
            sa.text(f"SELECT status, min_responden, catatan FROM {sesi_table} WHERE id = :id"),
            {"id": source_sesi_id},
        ).one_or_none()
        if row is not None:
            status = "OPEN" if row.status in ("DRAFT", "OPEN") else row.status
            min_responden = row.min_responden
            catatan = row.catatan

    connection.execute(
        sa.text(
            f"INSERT INTO {instrumen_table} (id, status, min_responden, catatan, created_at) "
            "VALUES (:id, :status, :min_responden, :catatan, now())"
        ),
        {"id": instrumen_id, "status": status, "min_responden": min_responden, "catatan": catatan},
    )


def upgrade() -> None:
    connection = op.get_bind()

    # 1) Buat tabel instrumen singleton (DCS & WCP).
    op.create_table(
        "dcs_instrumen",
        sa.Column("id", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("min_responden", sa.Integer(), nullable=False),
        sa.Column("catatan", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dcs_instrumen")),
    )
    op.create_index(
        op.f("ix_dcs_instrumen_created_at"), "dcs_instrumen", ["created_at"], unique=False
    )
    op.create_table(
        "wcp_instrumen",
        sa.Column("id", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("min_responden", sa.Integer(), nullable=False),
        sa.Column("catatan", sa.Text(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wcp_instrumen")),
    )
    op.create_index(
        op.f("ix_wcp_instrumen_created_at"), "wcp_instrumen", ["created_at"], unique=False
    )

    # 2) Guard + backfill satu baris instrumen dari sesi ber-responden (bila ada).
    _seed_instrumen(
        connection,
        modul="DCS",
        sesi_table="dcs_sesi",
        responden_table="dcs_responden",
        instrumen_table="dcs_instrumen",
        instrumen_id="dcs",
    )
    _seed_instrumen(
        connection,
        modul="WCP",
        sesi_table="wcp_sesi",
        responden_table="wcp_responden",
        instrumen_table="wcp_instrumen",
        instrumen_id="wcp",
    )

    # 3) Lepas sesi_id dari responden; partisipan_id menjadi unik (DCS).
    op.drop_index(op.f("ix_dcs_responden_partisipan_id"), table_name="dcs_responden")
    op.drop_index(op.f("ix_dcs_responden_sesi_id"), table_name="dcs_responden")
    op.create_unique_constraint(
        op.f("uq_dcs_responden_partisipan_id"), "dcs_responden", ["partisipan_id"]
    )
    op.drop_constraint(
        op.f("fk_dcs_responden_sesi_id_dcs_sesi"), "dcs_responden", type_="foreignkey"
    )
    op.drop_column("dcs_responden", "sesi_id")

    # 4) Idem WCP.
    op.drop_index(op.f("ix_wcp_responden_partisipan_id"), table_name="wcp_responden")
    op.drop_index(op.f("ix_wcp_responden_sesi_id"), table_name="wcp_responden")
    op.create_unique_constraint(
        op.f("uq_wcp_responden_partisipan_id"), "wcp_responden", ["partisipan_id"]
    )
    op.drop_constraint(
        op.f("fk_wcp_responden_sesi_id_wcp_sesi"), "wcp_responden", type_="foreignkey"
    )
    op.drop_column("wcp_responden", "sesi_id")

    # 5) Tabel sesi lama tidak lagi dipakai.
    op.drop_index(op.f("ix_dcs_sesi_created_at"), table_name="dcs_sesi")
    op.drop_table("dcs_sesi")
    op.drop_index(op.f("ix_wcp_sesi_created_at"), table_name="wcp_sesi")
    op.drop_table("wcp_sesi")


def downgrade() -> None:
    # ### best-effort — data instrumen singleton & tautan sesi-responden TIDAK
    # direkonstruksi (lihat docstring modul). Struktur tabel lama dipulihkan KOSONG. ###
    op.create_table(
        "dcs_sesi",
        sa.Column("id", sa.VARCHAR(length=40), autoincrement=False, nullable=False),
        sa.Column("periode", sa.VARCHAR(length=7), autoincrement=False, nullable=False),
        sa.Column("status", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("min_responden", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("max_responden", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("catatan", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dcs_sesi")),
    )
    op.create_index(op.f("ix_dcs_sesi_created_at"), "dcs_sesi", ["created_at"], unique=False)
    op.create_table(
        "wcp_sesi",
        sa.Column("id", sa.VARCHAR(length=40), autoincrement=False, nullable=False),
        sa.Column("periode", sa.VARCHAR(length=7), autoincrement=False, nullable=False),
        sa.Column("status", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("min_responden", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("max_responden", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("catatan", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_wcp_sesi")),
    )
    op.create_index(op.f("ix_wcp_sesi_created_at"), "wcp_sesi", ["created_at"], unique=False)

    op.add_column(
        "dcs_responden",
        sa.Column("sesi_id", sa.VARCHAR(length=40), autoincrement=False, nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_dcs_responden_sesi_id_dcs_sesi"),
        "dcs_responden",
        "dcs_sesi",
        ["sesi_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(op.f("uq_dcs_responden_partisipan_id"), "dcs_responden", type_="unique")
    op.create_index(op.f("ix_dcs_responden_sesi_id"), "dcs_responden", ["sesi_id"], unique=False)
    op.create_index(
        op.f("ix_dcs_responden_partisipan_id"), "dcs_responden", ["partisipan_id"], unique=False
    )

    op.add_column(
        "wcp_responden",
        sa.Column("sesi_id", sa.VARCHAR(length=40), autoincrement=False, nullable=True),
    )
    op.create_foreign_key(
        op.f("fk_wcp_responden_sesi_id_wcp_sesi"),
        "wcp_responden",
        "wcp_sesi",
        ["sesi_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint(op.f("uq_wcp_responden_partisipan_id"), "wcp_responden", type_="unique")
    op.create_index(op.f("ix_wcp_responden_sesi_id"), "wcp_responden", ["sesi_id"], unique=False)
    op.create_index(
        op.f("ix_wcp_responden_partisipan_id"), "wcp_responden", ["partisipan_id"], unique=False
    )

    op.drop_index(op.f("ix_wcp_instrumen_created_at"), table_name="wcp_instrumen")
    op.drop_table("wcp_instrumen")
    op.drop_index(op.f("ix_dcs_instrumen_created_at"), table_name="dcs_instrumen")
    op.drop_table("dcs_instrumen")
