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


class _SubjectVerifier:
    """Verifier test yang menerima semua token sebagai `Principal(subject, groups)` tetap."""

    def __init__(self, subject: str, groups: list[str] | None = None) -> None:
        self._subject = subject
        self._groups = groups if groups is not None else ["partisipan"]

    def verify(self, token: str) -> Principal:
        return Principal(subject=self._subject, username=self._subject, groups=self._groups)


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


@pytest.fixture
def client_as(app):
    """Factory: ``client_as(subject, groups=["partisipan"]) -> TestClient``.

    Mengoverride verifier token pada `app` agar SETIAP token diterima sebagai
    `Principal(subject, groups)` tetap — dipakai untuk test otorisasi object-level
    (BOLA/IDOR) yang butuh 2+ identitas partisipan berbeda dalam satu test. Peringatan:
    override berlaku pada `app` (bukan hanya client yang dikembalikan) — panggilan
    berikutnya ke fixture `client`/`anon_client` dalam test yang sama ikut memakai
    identitas terakhir yang di-set lewat factory ini. Untuk kebutuhan admin setelah
    memakai factory ini, panggil ``client_as("admin-x", groups=["admin"])`` alih-alih
    fixture `client`.
    """

    def _make(subject: str, groups: list[str] | None = None) -> TestClient:
        app.dependency_overrides[get_token_verifier] = lambda: _SubjectVerifier(subject, groups)
        c = TestClient(app, raise_server_exceptions=True)
        c.headers.update({"Authorization": f"Bearer {subject}-token"})
        return c

    return _make


@pytest.fixture
def partisipan_factory(db_session: Session):
    """Factory: ``partisipan_factory(subject, **overrides) -> partisipan_id``.

    Membuat record `Partisipan` nyata di DB test dengan `authentik_user_id=subject`,
    agar `PartisipanService.get_by_subject(subject)` (dipakai `authorize_responden_access`)
    dapat menemukannya — untuk test kepemilikan responden lintas partisipan.
    """
    import uuid

    from anjab_abk_backend.core.schemas.partisipan import PartisipanCreate
    from anjab_abk_backend.core.services.partisipan_sql import SqlPartisipanService

    svc = SqlPartisipanService(db_session)

    def _create(subject: str, **overrides) -> str:
        defaults = {
            "nama": f"Partisipan {subject}",
            "email": f"{subject.replace('_', '.')}@test.id",
            "sekolah_id": "skl_test",
            "jabatan_utama_id": f"jbt_{uuid.uuid4().hex[:8]}",
            "masa_kerja_tahun": 1,
        }
        defaults.update(overrides)
        par = svc.create(PartisipanCreate(**defaults), authentik_user_id=subject)
        return par.id

    return _create


@pytest.fixture
def jabatan_id_tk(client: TestClient) -> str:
    """Jabatan_id dari catalog kombinasi Task Inventory (unit selalu "ALL" sejak
    revisi master data Task Bank v2_19 — `unit` bukan lagi pembeda kombinasi).

    Dipakai bersama oleh `test_taskinv.py` dan test OPM (`_opm_common.py`) — satu
    sumber jabatan ber-catalog nyata (baris `jabatan` sungguhan, bukan ID acak).

    Memakai `client` (ber-token), bukan `anon_client`: sejak backlog 025 seluruh
    endpoint baca menuntut token.
    """
    kombis = client.get("/api/v1/task-inventory/catalog/kombinasi").json()
    match = next((x for x in kombis if x["unit"] == "ALL"), None)
    assert match is not None, "Tidak ada kombinasi dalam catalog"
    return match["jabatan_id"]
