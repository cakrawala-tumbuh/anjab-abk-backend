"""Alembic environment — terhubung ke DatabaseSettings & metadata model.

URL koneksi diambil dari `app.db.DatabaseSettings` (environment / `.env`), BUKAN
dari alembic.ini, agar rahasia tidak ter-commit (12-factor). `target_metadata`
menunjuk ke `app.models.Base.metadata` sehingga `alembic revision --autogenerate`
dapat membandingkan model ↔ schema.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from anjab_abk_backend.db import get_db_settings
from anjab_abk_backend.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Suntik URL dari settings (password hanya dipakai runtime, tidak ditulis ke file).
# Hormati URL yang sudah dipasang lewat Config (mis. `migrate.make_alembic_config(url)`
# untuk database sekali-pakai saat test) — hanya ambil dari environment bila kosong.
if not config.get_main_option("sqlalchemy.url"):
    _url = get_db_settings().sqlalchemy_url()
    config.set_main_option(
        "sqlalchemy.url",
        _url if isinstance(_url, str) else _url.render_as_string(hide_password=False),
    )


def run_migrations_offline() -> None:
    """Mode offline: hasilkan SQL tanpa koneksi (mis. untuk review/CI)."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Mode online: terapkan migrasi lewat koneksi nyata."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
