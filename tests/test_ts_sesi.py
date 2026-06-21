"""Test endpoint TsSesi: CRUD + transisi status."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/time-study/sesi"


def _payload(jabatan_id: str | None = None, periode: str | None = None) -> dict:
    return {
        "jabatan_id": jabatan_id or f"jbt_{uuid.uuid4().hex[:8]}",
        "periode": periode or "2025-06",
    }


@pytest.fixture
def created(client: TestClient) -> dict:
    r = client.post(BASE, json=_payload())
    assert r.status_code == 201
    return r.json()


def test_list_ok(anon_client: TestClient) -> None:
    r = anon_client.get(BASE)
    assert r.status_code == 200
    assert "items" in r.json()


def test_create_and_get(client: TestClient, created: dict) -> None:
    sesi_id = created["id"]
    assert sesi_id.startswith("tses_")
    assert created["status"] == "DRAFT"
    r = client.get(f"{BASE}/{sesi_id}")
    assert r.status_code == 200
    assert r.json()["id"] == sesi_id


def test_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(BASE, json=_payload())
    assert r.status_code == 401


def test_update_draft(client: TestClient, created: dict) -> None:
    r = client.patch(f"{BASE}/{created['id']}", json={"catatan": "Catatan baru"})
    assert r.status_code == 200
    assert r.json()["catatan"] == "Catatan baru"


def test_not_found(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE}/tses_tidakada")
    assert r.status_code == 404


def test_transition_draft_to_open(client: TestClient, created: dict) -> None:
    r = client.post(f"{BASE}/{created['id']}/buka")
    assert r.status_code == 200
    assert r.json()["status"] == "OPEN"


def test_transition_invalid(client: TestClient, created: dict) -> None:
    # Try tutup (OPEN→CLOSED) from DRAFT — should fail
    r = client.post(f"{BASE}/{created['id']}/tutup")
    assert r.status_code in (400, 422)


def test_full_lifecycle(client: TestClient) -> None:
    sesi = client.post(BASE, json=_payload()).json()
    sesi_id = sesi["id"]

    r = client.post(f"{BASE}/{sesi_id}/buka")
    assert r.json()["status"] == "OPEN"

    r = client.post(f"{BASE}/{sesi_id}/tutup")
    assert r.json()["status"] == "CLOSED"

    r = client.post(f"{BASE}/{sesi_id}/analisis")
    assert r.json()["status"] == "ANALYZED"


def test_delete_draft(client: TestClient) -> None:
    sesi = client.post(BASE, json=_payload()).json()
    r = client.delete(f"{BASE}/{sesi['id']}")
    assert r.status_code == 204
    assert client.get(f"{BASE}/{sesi['id']}").status_code == 404


def test_delete_non_draft_rejected(client: TestClient) -> None:
    sesi = client.post(BASE, json=_payload()).json()
    client.post(f"{BASE}/{sesi['id']}/buka")
    r = client.delete(f"{BASE}/{sesi['id']}")
    assert r.status_code in (400, 422)
