"""Mekanisme migrasi schema — runner Alembic terprogram (gaya Odoo).

Filosofi (seperti migrasi modul Odoo): **setiap perubahan struktur database adalah
satu berkas revisi tersendiri** di ``migrations/versions/`` — JANGAN menumpuk banyak
perubahan ke satu berkas dan JANGAN mengedit revisi yang sudah pernah berjalan di
lingkungan lain. Tiap revisi menyimpan ``down_revision`` sehingga membentuk rantai
yang terurut; Alembic menerapkannya bertahap (incremental) dari versi DB saat ini
menuju ``head``.

Modul ini menyediakan akses **terprogram** ke perintah Alembic agar mekanisme migrasi
bisa dipakai dari kode (mis. di startup/CLI) maupun diverifikasi oleh test — tanpa
harus menjalankan biner ``alembic`` lewat shell. URL koneksi mengikuti aturan
12-factor: bila tidak dioper eksplisit, ``migrations/env.py`` mengambilnya dari
``DatabaseSettings`` (environment), bukan dari ``alembic.ini``.

Alur membuat revisi baru saat model berubah::

    # 1. ubah model di models.py
    # 2. hasilkan revisi (butuh DB hidup untuk autogenerate)
    make migration m="tambah kolom catatan pada jabatan"
    # 3. REVIEW berkas baru di migrations/versions/, sesuaikan bila perlu
    # 4. terapkan
    alembic upgrade head

Test ``tests/test_migrations.py`` memaksa disiplin ini: bila model berubah tanpa
revisi baru, ``test_schema_matches_models`` gagal.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config

# migrate.py ada di src/anjab_abk_backend/ ; alembic.ini & migrations/ ada di root repo.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _PROJECT_ROOT / "alembic.ini"
_MIGRATIONS_DIR = _PROJECT_ROOT / "migrations"


def make_alembic_config(url: str | None = None) -> Config:
    """Bangun objek ``Config`` Alembic yang menunjuk ke ``alembic.ini`` & ``migrations/``.

    ``script_location`` di-set absolut agar berjalan dari direktori kerja manapun
    (test runner, container, CLI). Bila ``url`` diberikan, ia dipasang sebagai
    ``sqlalchemy.url`` dan ``env.py`` akan menghormatinya (tidak menimpa dengan nilai
    dari environment) — berguna untuk mengarahkan migrasi ke database sekali-pakai
    saat test.
    """
    config = Config(str(_ALEMBIC_INI))
    config.set_main_option("script_location", str(_MIGRATIONS_DIR))
    if url is not None:
        config.set_main_option("sqlalchemy.url", url)
    return config


def upgrade(url: str | None = None, revision: str = "head") -> None:
    """Terapkan migrasi maju sampai ``revision`` (default ``head``)."""
    from alembic import command

    command.upgrade(make_alembic_config(url), revision)


def downgrade(url: str | None = None, revision: str = "-1") -> None:
    """Mundurkan migrasi ke ``revision`` (default satu langkah; ``base`` = kosong)."""
    from alembic import command

    command.downgrade(make_alembic_config(url), revision)


def current_heads(url: str | None = None) -> list[str]:
    """Kembalikan daftar revisi ``head`` yang terdefinisi di ``migrations/versions/``.

    Lebih dari satu head berarti ada cabang divergen yang harus di-*merge* lebih dulu.
    """
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(make_alembic_config(url))
    return list(script.get_heads())
