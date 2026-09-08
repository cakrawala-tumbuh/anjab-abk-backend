"""backfill cabang sekolah dari provinsi

Revision ID: dd4050714517
Revises: 3ae579a1e435
Create Date: 2026-09-08 15:38:21.831563

Backlog `anjab-abk-backend#40`, lanjutan langsung `3ae579a1e435` (disiplin satu
perubahan/berkas: DDL lalu data). Mengisi kolom `sekolah.cabang` yang ditambahkan
revisi sebelumnya untuk baris `sekolah` yang sudah ada, memakai `provinsi` sebagai
proksi satu-kalinya (opsi yang DITOLAK sebagai penentu cabang permanen — lihat
lampiran `alternatif` issue #40 — tetapi sah dipakai SEKALI di sini, sebagai sumber
backfill, karena konsisten dengan seluruh 17 baris sekolah produksi YPII per audit
2026-09-08):

`provinsi = 'Jawa Barat'` -> `cabang = 'Bandung'`; `provinsi = 'Jawa Tengah'` ->
`cabang = 'Semarang'`. Provinsi lain (mis. Bali) dibiarkan `NULL` — TIDAK ditebak.

`upgrade()` menulis **hanya** baris ber-`cabang IS NULL` sehingga nilai yang sudah
diisi manual (lewat API, sebelum migrasi ini berjalan) TIDAK tertimpa. Aman
dijalankan di database kosong (0 baris terpengaruh, bukan error).

`downgrade()` adalah kebalikannya: mengosongkan kembali ke `NULL` **hanya** untuk
baris yang `cabang` saat itu masih PERSIS sama dengan hasil pemetaan
provinsi->cabang di atas (mencegah menimpa nilai yang sengaja diubah manual
setelah migrasi ini berjalan). Ketidakcocokan (provinsi cocok tapi cabang sudah
berbeda) dicatat lewat `logging.warning`, TIDAK menggagalkan migrasi.
"""

from __future__ import annotations

from collections.abc import Sequence
from logging import getLogger

import sqlalchemy as sa
from alembic import op

revision: str = "dd4050714517"
down_revision: str | None = "3ae579a1e435"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

logger = getLogger(__name__)

# Pemetaan provinsi -> cabang. Sumber tunggal di migrasi ini — TIDAK direplikasi di
# kode aplikasi (lihat lampiran `alternatif` issue #40: opsi "provinsi sebagai
# penentu cabang langsung" ditolak justru karena akan menyebarkan pemetaan tak
# tertulis ke tiap titik yang menyaring).
_PEMETAAN = {"Jawa Barat": "Bandung", "Jawa Tengah": "Semarang"}

_UPGRADE_SQL = sa.text(
    "UPDATE sekolah SET cabang = :cabang WHERE provinsi = :provinsi AND cabang IS NULL"
)

_DOWNGRADE_SQL = sa.text(
    "UPDATE sekolah SET cabang = NULL WHERE provinsi = :provinsi AND cabang = :cabang"
)

# Baris ber-provinsi cocok tapi cabang-nya SUDAH diisi (upgrade) / sudah berbeda dari
# hasil pemetaan (downgrade) — dihitung terpisah agar ketidakcocokan bisa dilaporkan
# tanpa menggagalkan migrasi, mengikuti preseden `ad595b80d3d1`.
_UPGRADE_KETIDAKCOCOKAN_SQL = sa.text(
    "SELECT COUNT(*) FROM sekolah WHERE provinsi = :provinsi AND cabang IS NOT NULL"
)

_DOWNGRADE_KETIDAKCOCOKAN_SQL = sa.text(
    "SELECT COUNT(*) FROM sekolah "
    "WHERE provinsi = :provinsi AND cabang IS NOT NULL AND cabang != :cabang"
)


def upgrade() -> None:
    conn = op.get_bind()
    total = 0
    tidak_cocok = 0
    for provinsi, cabang in _PEMETAAN.items():
        result = conn.execute(_UPGRADE_SQL, {"provinsi": provinsi, "cabang": cabang})
        total += result.rowcount
        tidak_cocok += conn.execute(
            _UPGRADE_KETIDAKCOCOKAN_SQL, {"provinsi": provinsi}
        ).scalar_one()
    logger.info(
        "Migrasi dd4050714517: %d baris sekolah di-backfill cabang dari provinsi.",
        total,
    )
    if tidak_cocok:
        logger.warning(
            "Migrasi dd4050714517: %d baris sekolah ber-provinsi cocok dilewati karena "
            "cabang sudah terisi manual — tidak ditimpa.",
            tidak_cocok,
        )


def downgrade() -> None:
    conn = op.get_bind()
    total = 0
    tidak_cocok = 0
    for provinsi, cabang in _PEMETAAN.items():
        result = conn.execute(_DOWNGRADE_SQL, {"provinsi": provinsi, "cabang": cabang})
        total += result.rowcount
        tidak_cocok += conn.execute(
            _DOWNGRADE_KETIDAKCOCOKAN_SQL, {"provinsi": provinsi, "cabang": cabang}
        ).scalar_one()
    logger.info(
        "Migrasi dd4050714517 (downgrade): %d baris sekolah dikosongkan kembali ke " "cabang NULL.",
        total,
    )
    if tidak_cocok:
        logger.warning(
            "Migrasi dd4050714517 (downgrade): %d baris sekolah dilewati karena cabang "
            "sudah berbeda dari hasil pemetaan provinsi->cabang — tidak dikosongkan.",
            tidak_cocok,
        )
