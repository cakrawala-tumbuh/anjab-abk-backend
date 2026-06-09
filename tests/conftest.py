"""Fixtures pytest untuk anjab-abk-backend."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from anjab_abk_backend.config import Settings
from anjab_abk_backend.dependencies import get_token_verifier
from anjab_abk_backend.main import create_app
from anjab_abk_backend.security import Principal, TokenVerifier


class _FakeVerifier:
    """Verifier test yang menerima semua token."""

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
def app(settings: Settings):
    a = create_app(settings=settings)
    a.dependency_overrides[get_token_verifier] = _fake_verifier
    return a


@pytest.fixture(scope="session")
def anon_client(app) -> TestClient:
    """Client tanpa token."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(scope="session")
def client(app) -> TestClient:
    """Client dengan Bearer token — dioverride pakai _FakeVerifier."""
    with TestClient(app, raise_server_exceptions=True) as c:
        c.headers.update({"Authorization": "Bearer test-token"})
        yield c
