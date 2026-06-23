"""Koneksi PostgreSQL: engine, connection pool, dan sesi per-request.

Modul ini MENGISI seam yang sengaja dibiarkan kosong oleh backend-skill
(`lifespan_resources` di main.py dan provider service di dependencies.py).
Engine dibuat **lazy** (saat sesi pertama dibutuhkan), memakai SQLAlchemy 2.0
(sync) + driver psycopg 3 — cocok dengan kontrak service yang **sinkron** di
backend-skill (router memanggil `service.list(...)` tanpa `await`; FastAPI
menjalankan endpoint `def` di threadpool sehingga I/O blocking DB tidak
memblok event loop).

Konfigurasi dibaca dari environment lewat `DatabaseSettings` yang TERPISAH dari
`anjab_abk_backend.config.Settings` agar overlay ini tidak perlu menyunting
config.py. Tim boleh saja menggabungkannya ke `Settings` utama bila ingin satu
sumber konfigurasi.

Pooling disetel untuk PostgreSQL: `pool_pre_ping` (deteksi koneksi yang sudah
ditutup server/pooler seperti PgBouncer) dan `pool_recycle` (daur ulang koneksi
idle sebelum dropped oleh proxy/cloud LB).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger("anjab_abk_backend.db")


class DatabaseSettings(BaseSettings):
    """Konfigurasi koneksi PostgreSQL (12-factor, dibaca dari environment / `.env`).

    Sediakan `DATABASE_URL` lengkap, ATAU komponen `DB_HOST`/`DB_PORT`/`DB_USER`/
    `DB_PASSWORD`/`DB_NAME`. Bila `DATABASE_URL` diisi, ia menang.
    """

    database_url: str | None = None
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_user: str = "app"
    db_password: SecretStr = SecretStr("")
    db_name: str = "app"

    db_pool_size: int = 5
    db_max_overflow: int = 10
    db_pool_recycle: int = 1800
    db_pool_pre_ping: bool = True
    db_pool_timeout: int = 30
    db_connect_timeout: int = 10
    db_echo: bool = False

    # TTL hasil idempotency (detik); 0 = tanpa kedaluwarsa (lihat services/idempotency_sql.py).
    db_idempotency_ttl_seconds: int = 86400

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        case_sensitive=False,
        extra="ignore",  # abaikan variabel app non-DB di .env yang sama
    )

    def sqlalchemy_url(self) -> URL | str:
        """Bangun URL SQLAlchemy: pakai `database_url` apa adanya, atau rakit dari komponen.

        ``URL.create`` meng-escape kredensial otomatis — jangan merakit string DSN
        secara manual (karakter khusus pada password bisa merusak URL).
        """
        if self.database_url:
            return self.database_url
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


@lru_cache
def get_db_settings() -> DatabaseSettings:
    """Kembalikan DatabaseSettings yang di-cache (singleton proses)."""
    return DatabaseSettings()


@lru_cache
def get_engine() -> Engine:
    """Buat (lazy) dan kembalikan Engine SQLAlchemy singleton.

    Catatan PgBouncer (transaction pooling): psycopg 3 memakai server-side prepared
    statement secara default. Bila di belakang PgBouncer mode `transaction`, tambahkan
    ``"prepare_threshold": None`` ke ``connect_args`` — atau pakai mode `session`.
    """
    s = get_db_settings()
    return create_engine(
        s.sqlalchemy_url(),
        pool_size=s.db_pool_size,
        max_overflow=s.db_max_overflow,
        pool_recycle=s.db_pool_recycle,
        pool_pre_ping=s.db_pool_pre_ping,
        pool_timeout=s.db_pool_timeout,
        echo=s.db_echo,
        connect_args={"connect_timeout": s.db_connect_timeout},
    )


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    """Kembalikan factory sesi (lazy, singleton). `expire_on_commit=False` agar
    objek tetap bisa dibaca setelah commit di teardown dependency."""
    return sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Unit-of-work: satu sesi per blok; commit bila sukses, rollback bila gagal."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session() -> Iterator[Session]:
    """SEAM DI: sesi DB per-request (generator dependency).

    Karena FastAPI men-cache hasil dependency dalam satu request, SEMUA service
    yang `Depends(get_session)` berbagi **satu** sesi → satu transaksi/unit-of-work
    per request. Commit/rollback terjadi di teardown setelah respons terbentuk.
    """
    with session_scope() as session:
        yield session


def ping() -> None:
    """Jalankan ``SELECT 1`` untuk membuktikan DB hidup & dapat dijangkau."""
    with get_engine().connect() as conn:
        conn.execute(text("SELECT 1"))


def init_engine() -> None:
    """Hangatkan engine saat startup (opsional). Aman dipanggil dari lifespan."""
    get_engine()
    logger.info("db engine siap")


def dispose_engine() -> None:
    """Tutup semua koneksi pool saat shutdown (graceful). Panggil dari lifespan."""
    get_engine().dispose()
    logger.info("db engine dilepas")
