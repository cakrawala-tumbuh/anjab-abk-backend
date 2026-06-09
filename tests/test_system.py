"""Test endpoint sistem: health, readiness, version, me, OpenAPI."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health(anon_client: TestClient) -> None:
    r = anon_client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_ready(anon_client: TestClient) -> None:
    r = anon_client.get("/api/v1/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_version(anon_client: TestClient) -> None:
    r = anon_client.get("/api/v1/version")
    assert r.status_code == 200
    assert "version" in r.json()


def test_me_unauthorized(anon_client: TestClient) -> None:
    r = anon_client.get("/api/v1/me")
    assert r.status_code == 401
    assert r.headers.get("WWW-Authenticate") == "Bearer"


def test_me_authorized(client: TestClient) -> None:
    r = client.get("/api/v1/me")
    assert r.status_code == 200
    data = r.json()
    assert data["subject"] == "test-user"


def test_openapi_json(anon_client: TestClient) -> None:
    r = anon_client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert "paths" in schema
    assert schema["info"]["title"]


def test_swagger_docs(anon_client: TestClient) -> None:
    r = anon_client.get("/docs")
    assert r.status_code == 200


def test_redoc(anon_client: TestClient) -> None:
    r = anon_client.get("/redoc")
    assert r.status_code == 200


def test_request_id_header_present(anon_client: TestClient) -> None:
    r = anon_client.get("/api/v1/health")
    assert "x-request-id" in r.headers
