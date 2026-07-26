"""tolak responden ganda per partisipan per sesi TI

Revision ID: 79edf4fa66b1
Revises: 92f6851d040c
Create Date: 2026-07-26 11:46:22.589193

Backlog `anjab-abk-backend#29`. Satu partisipan bisa terdaftar dua kali sebagai
responden pada sesi Task Inventory yang sama (`SqlTiRespondenService.create()`
langsung `INSERT` tanpa cek duplikat) — merusak diam-diam gerbang `mulai-tahap2`,
`unanimous_terpilih`, dan `fmean` ABK (menghitung/membobot satu orang dua kali).

Sebelum menambah `UniqueConstraint("sesi_id", "partisipan_id")`
(`uq_ti_responden_sesi_partisipan`), migrasi ini membersihkan duplikat lama:
untuk tiap grup `(sesi_id, partisipan_id)` (`partisipan_id` non-NULL) berisi >1
baris, baris yang **pertahankan** adalah yang `tahap1_submit`/`tahap3_submit`
bernilai true; bila tidak ada yang submit, baris `created_at` paling awal.
Baris sisanya dihapus **hanya bila** kedua flag submit-nya false DAN tidak
punya baris anak di `ti_seleksi`/`ti_detail`/`ti_usulan_task` — bila ada baris
yang tidak memenuhi syarat itu (sudah submit atau punya jawaban tersimpan),
migrasi **gagal** (`RuntimeError`) menyebut `id` responden bersangkutan;
jawaban partisipan tidak boleh terhapus diam-diam oleh migrasi ini.

`partisipan_id = NULL` (responden manual tanpa partisipan) tidak pernah masuk
pembersihan ini — PostgreSQL memperlakukan NULL sebagai distinct pada unique
constraint sehingga boleh berulang tanpa perlu partial index.

``downgrade()`` hanya melepas constraint; baris yang sudah dihapus TIDAK
dikembalikan (tidak ada snapshot data yang bisa direstorasi).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "79edf4fa66b1"
down_revision: str | None = "92f6851d040c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _hitung_baris_anak(conn: sa.Connection, responden_id: str) -> int:
    """Jumlah baris anak `responden_id` di `ti_seleksi`+`ti_detail`+`ti_usulan_task`.

    Dipakai untuk menentukan apakah sebuah baris `ti_responden` duplikat aman
    dihapus (0 baris anak) atau harus mengagalkan migrasi (≥1 baris anak, berarti
    ada jawaban tersimpan yang tidak boleh hilang diam-diam).
    """
    return conn.execute(
        sa.text(
            "SELECT "
            "(SELECT count(*) FROM ti_seleksi WHERE responden_id = :rid) "
            "+ (SELECT count(*) FROM ti_detail WHERE responden_id = :rid) "
            "+ (SELECT count(*) FROM ti_usulan_task WHERE responden_id = :rid)"
        ),
        {"rid": responden_id},
    ).scalar_one()


def _bersihkan_duplikat_ti_responden(conn: sa.Connection) -> None:
    """Hapus baris `ti_responden` duplikat lama sesuai aturan di docstring modul.

    Raises:
        RuntimeError: bila ada baris duplikat yang sudah submit (Tahap 1/3) atau
            punya baris anak — baris semacam itu tidak boleh dihapus otomatis,
            migrasi berhenti dan menyebut `id` responden yang bentrok agar
            diselesaikan manual sebelum dijalankan ulang.
    """
    dup_groups = conn.execute(
        sa.text(
            "SELECT sesi_id, partisipan_id FROM ti_responden "
            "WHERE partisipan_id IS NOT NULL "
            "GROUP BY sesi_id, partisipan_id HAVING count(*) > 1"
        )
    ).all()

    for sesi_id, partisipan_id in dup_groups:
        rows = conn.execute(
            sa.text(
                "SELECT id, tahap1_submit, tahap3_submit, created_at FROM ti_responden "
                "WHERE sesi_id = :sesi_id AND partisipan_id = :partisipan_id "
                "ORDER BY created_at ASC"
            ),
            {"sesi_id": sesi_id, "partisipan_id": partisipan_id},
        ).all()

        submitted = [r for r in rows if r.tahap1_submit or r.tahap3_submit]
        keeper_id = (submitted[0] if submitted else rows[0]).id
        losers = [r for r in rows if r.id != keeper_id]

        for loser in losers:
            if loser.tahap1_submit or loser.tahap3_submit:
                raise RuntimeError(
                    f"Migrasi 79edf4fa66b1 gagal: responden '{loser.id}' duplikat "
                    f"(sesi_id={sesi_id!r}, partisipan_id={partisipan_id!r}) sudah "
                    "menyelesaikan Tahap 1/3 — tidak boleh dihapus otomatis oleh "
                    "migrasi ini. Selesaikan duplikatnya secara manual, lalu jalankan "
                    "ulang migrasi."
                )
            if _hitung_baris_anak(conn, loser.id) > 0:
                raise RuntimeError(
                    f"Migrasi 79edf4fa66b1 gagal: responden '{loser.id}' duplikat "
                    f"(sesi_id={sesi_id!r}, partisipan_id={partisipan_id!r}) punya "
                    "baris anak (ti_seleksi/ti_detail/ti_usulan_task) — tidak boleh "
                    "dihapus otomatis oleh migrasi ini. Selesaikan duplikatnya "
                    "secara manual, lalu jalankan ulang migrasi."
                )
            conn.execute(sa.text("DELETE FROM ti_responden WHERE id = :rid"), {"rid": loser.id})


def upgrade() -> None:
    conn = op.get_bind()
    _bersihkan_duplikat_ti_responden(conn)
    op.create_unique_constraint(
        "uq_ti_responden_sesi_partisipan", "ti_responden", ["sesi_id", "partisipan_id"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_ti_responden_sesi_partisipan", "ti_responden", type_="unique")
