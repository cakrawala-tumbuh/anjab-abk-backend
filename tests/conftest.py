"""Fixtures pytest untuk anjab-abk-backend (integrasi PostgreSQL).

Pola isolasi: schema dibuat sekali per sesi test + master data di-seed (DCS sub-skala,
WCP dimensi, katalog Task Inventory). Tiap test memakai SATU koneksi dengan transaksi
luar yang DI-ROLLBACK di akhir (`join_transaction_mode="create_savepoint"` membuat
`commit()` aplikasi menjadi RELEASE SAVEPOINT) → tidak ada artefak antar-test.

URL DB test diambil dari environment (`DATABASE_URL` / `DB_*`), disediakan oleh harness
`automated-test` (service PostgreSQL di Docker). Override `get_session` mengarahkan
SELURUH seam data ke sesi test sekaligus.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from anjab_abk_backend.config import Settings
from anjab_abk_backend.db import get_db_settings, get_session
from anjab_abk_backend.dependencies import get_token_verifier
from anjab_abk_backend.main import create_app
from anjab_abk_backend.migrate import upgrade as alembic_upgrade
from anjab_abk_backend.models import Base
from anjab_abk_backend.security import Principal, TokenVerifier
from anjab_abk_backend.seed_db import seed_all


class _FakeVerifier:
    """Verifier test yang menerima semua token (principal admin)."""

    def verify(self, token: str) -> Principal:
        return Principal(subject="test-user", username="tester", groups=["admin"])


def _fake_verifier() -> TokenVerifier:
    return _FakeVerifier()


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings(
        docs_enabled=True,
        cors_origins=[],
        allowed_hosts=["*"],
        require_if_match=False,
    )


@pytest.fixture(scope="session")
def engine():
    """Engine ke DB test: schema dibangun lewat MIGRASI Alembic (bukan ``create_all``)
    lalu master data di-seed, sekali per sesi; drop di akhir.

    Membangun schema dengan ``alembic upgrade head`` membuat SETIAP run test ikut
    memverifikasi rantai migrasi (gaya Odoo: DB test dibangun dengan menjalankan
    migrasi). Bila migrasi rusak/tertinggal dari model, test akan gagal sejak setup.
    """
    db_url = str(get_db_settings().sqlalchemy_url())
    alembic_upgrade(db_url, "head")
    eng = create_engine(db_url)
    with Session(eng) as s:
        seed_all(s)
        s.commit()
    try:
        yield eng
    finally:
        Base.metadata.drop_all(eng)
        eng.dispose()


@pytest.fixture
def db_session(engine):
    """Sesi terisolasi-transaksi: semua perubahan test di-rollback setelahnya."""
    connection = engine.connect()
    trans = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def app(settings: Settings, db_session: Session):
    a = create_app(settings=settings)

    def _override_session():
        yield db_session  # lifecycle dikelola fixtur db_session (tanpa commit/close)

    a.dependency_overrides[get_session] = _override_session
    a.dependency_overrides[get_token_verifier] = _fake_verifier
    return a


@pytest.fixture
def anon_client(app) -> TestClient:
    """Client tanpa token."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def client(app) -> TestClient:
    """Client dengan Bearer token — dioverride pakai _FakeVerifier."""
    with TestClient(app, raise_server_exceptions=True) as c:
        c.headers.update({"Authorization": "Bearer test-token"})
        yield c
