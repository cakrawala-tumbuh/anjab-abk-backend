"""ts: hapus sesi, penugasan berbasis partisipan

Revision ID: 0a58616358f4
Revises: c822a30d6b39
Create Date: 2026-07-04 07:09:24.368236

Time Study tidak lagi memakai sesi. Mekanisme assign partisipan disederhanakan
menjadi tabel `ts_penugasan` (satu baris per partisipan, flag `aktif`); `ts_log`
dikaitkan langsung ke `partisipan_id` (bukan lagi `responden_id`).

Backfill data lama:
1. `ts_penugasan` diisi dari `ts_responden` ber-`partisipan_id` (satu penugasan per
   partisipan, `created_at` diambil dari pendaftaran responden paling awal).
2. `ts_log.partisipan_id` diisi dari `ts_responden.partisipan_id` lewat join
   `responden_id`.
3. Log milik responden ANONIM (`partisipan_id IS NULL`) tidak dapat dipetakan ke
   partisipan manapun — baris tersebut DIHAPUS. Sebelum menjalankan migrasi ini di
   lingkungan produksi, pastikan tidak ada log Time Study anonim yang perlu
   dipertahankan.
4. Constraint unik lama `(responden_id, tanggal)` berubah jadi `(partisipan_id,
   tanggal)` — lebih ketat, karena satu partisipan dulu bisa terdaftar sebagai
   responden di beberapa sesi berbeda dengan tanggal log yang sama. Baris duplikat
   di-dedup, menyisakan baris dengan `updated_at` paling baru.

Downgrade dari revisi ini best-effort: struktur tabel lama dipulihkan, namun data
`ts_sesi`/`ts_responden` yang sudah dihapus TIDAK direkonstruksi.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0a58616358f4"
down_revision: str | None = "c822a30d6b39"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ts_penugasan",
        sa.Column("id", sa.String(length=40), nullable=False),
        sa.Column("partisipan_id", sa.String(length=40), nullable=False),
        sa.Column("aktif", sa.Boolean(), nullable=False),
        sa.Column("catatan", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ts_penugasan")),
    )
    op.create_index(
        op.f("ix_ts_penugasan_created_at"), "ts_penugasan", ["created_at"], unique=False
    )
    op.create_index(
        op.f("ix_ts_penugasan_partisipan_id"), "ts_penugasan", ["partisipan_id"], unique=True
    )

    connection = op.get_bind()

    # 1) Backfill ts_penugasan dari ts_responden ber-partisipan_id (satu / partisipan).
    connection.execute(
        sa.text(
            """
            INSERT INTO ts_penugasan (id, partisipan_id, aktif, catatan, created_at)
            SELECT
                'tpn_' || substr(md5(random()::text || clock_timestamp()::text), 1, 8),
                partisipan_id,
                true,
                NULL,
                MIN(created_at)
            FROM ts_responden
            WHERE partisipan_id IS NOT NULL
            GROUP BY partisipan_id
            """
        )
    )

    # 2) Tambah kolom partisipan_id di ts_log (nullable dulu untuk backfill).
    op.add_column("ts_log", sa.Column("partisipan_id", sa.String(length=40), nullable=True))
    connection.execute(
        sa.text(
            """
            UPDATE ts_log
            SET partisipan_id = ts_responden.partisipan_id
            FROM ts_responden
            WHERE ts_log.responden_id = ts_responden.id
            """
        )
    )

    # 3) Log dari responden anonim tak bisa dipetakan ke partisipan — dihapus.
    connection.execute(sa.text("DELETE FROM ts_log WHERE partisipan_id IS NULL"))

    # 4) Dedup (partisipan_id, tanggal): sisakan baris ber-updated_at paling baru.
    connection.execute(
        sa.text(
            """
            DELETE FROM ts_log
            WHERE id IN (
                SELECT id FROM (
                    SELECT id,
                           ROW_NUMBER() OVER (
                               PARTITION BY partisipan_id, tanggal
                               ORDER BY updated_at DESC, id DESC
                           ) AS rn
                    FROM ts_log
                ) ranked
                WHERE rn > 1
            )
            """
        )
    )

    op.alter_column("ts_log", "partisipan_id", nullable=False)

    op.drop_index(op.f("ix_ts_responden_created_at"), table_name="ts_responden")
    op.drop_index(op.f("ix_ts_responden_partisipan_id"), table_name="ts_responden")
    op.drop_index(op.f("ix_ts_responden_sesi_id"), table_name="ts_responden")
    op.drop_table("ts_responden")
    op.drop_index(op.f("ix_ts_sesi_created_at"), table_name="ts_sesi")
    op.drop_index(op.f("ix_ts_sesi_jabatan_id"), table_name="ts_sesi")
    op.drop_table("ts_sesi")
    op.drop_index(op.f("ix_ts_log_responden_id"), table_name="ts_log")
    op.drop_constraint(op.f("uq_ts_log_responden_id"), "ts_log", type_="unique")
    op.create_index(op.f("ix_ts_log_partisipan_id"), "ts_log", ["partisipan_id"], unique=False)
    op.create_unique_constraint(
        op.f("uq_ts_log_partisipan_id"), "ts_log", ["partisipan_id", "tanggal"]
    )
    op.drop_column("ts_log", "responden_id")


def downgrade() -> None:
    # ### best-effort — data ts_sesi/ts_responden TIDAK direkonstruksi ###
    op.add_column(
        "ts_log",
        sa.Column("responden_id", sa.VARCHAR(length=40), autoincrement=False, nullable=True),
    )
    op.drop_constraint(op.f("uq_ts_log_partisipan_id"), "ts_log", type_="unique")
    op.drop_index(op.f("ix_ts_log_partisipan_id"), table_name="ts_log")
    op.create_index(op.f("ix_ts_log_responden_id"), "ts_log", ["responden_id"], unique=False)
    op.drop_column("ts_log", "partisipan_id")
    op.create_table(
        "ts_sesi",
        sa.Column("id", sa.VARCHAR(length=40), autoincrement=False, nullable=False),
        sa.Column("jabatan_id", sa.VARCHAR(length=40), autoincrement=False, nullable=False),
        sa.Column("periode", sa.VARCHAR(length=7), autoincrement=False, nullable=False),
        sa.Column("status", sa.VARCHAR(length=20), autoincrement=False, nullable=False),
        sa.Column("catatan", sa.TEXT(), autoincrement=False, nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ts_sesi")),
    )
    op.create_index(op.f("ix_ts_sesi_jabatan_id"), "ts_sesi", ["jabatan_id"], unique=False)
    op.create_index(op.f("ix_ts_sesi_created_at"), "ts_sesi", ["created_at"], unique=False)
    op.create_table(
        "ts_responden",
        sa.Column("id", sa.VARCHAR(length=40), autoincrement=False, nullable=False),
        sa.Column("sesi_id", sa.VARCHAR(length=40), autoincrement=False, nullable=False),
        sa.Column("nama", sa.VARCHAR(length=200), autoincrement=False, nullable=True),
        sa.Column("jabatan_label", sa.VARCHAR(length=200), autoincrement=False, nullable=False),
        sa.Column("partisipan_id", sa.VARCHAR(length=40), autoincrement=False, nullable=True),
        sa.Column(
            "created_at", postgresql.TIMESTAMP(timezone=True), autoincrement=False, nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ts_responden")),
    )
    op.create_index(op.f("ix_ts_responden_sesi_id"), "ts_responden", ["sesi_id"], unique=False)
    op.create_index(
        op.f("ix_ts_responden_partisipan_id"), "ts_responden", ["partisipan_id"], unique=False
    )
    op.create_index(
        op.f("ix_ts_responden_created_at"), "ts_responden", ["created_at"], unique=False
    )
    op.drop_index(op.f("ix_ts_penugasan_partisipan_id"), table_name="ts_penugasan")
    op.drop_index(op.f("ix_ts_penugasan_created_at"), table_name="ts_penugasan")
    op.drop_table("ts_penugasan")
