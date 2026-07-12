"""Test endpoint DcsSesi: CRUD + transisi status."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/dcs/sesi"


def _payload(periode: str | None = None) -> dict:
    return {
        "periode": periode or "2025-06",
        "min_responden": 6,
        "max_responden": 8,
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
    assert sesi_id.startswith("dses_")
    assert created["status"] == "DRAFT"
    r = client.get(f"{BASE}/{sesi_id}")
    assert r.status_code == 200
    assert r.json()["id"] == sesi_id


def test_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(BASE, json=_payload())
    assert r.status_code == 401


def test_multiple_sesi_same_periode_allowed(client: TestClient, created: dict) -> None:
    r = client.post(BASE, json=_payload(periode=created["periode"]))
    assert r.status_code == 201


def test_update_draft(client: TestClient, created: dict) -> None:
    r = client.patch(f"{BASE}/{created['id']}", json={"catatan": "Screening awal"})
    assert r.status_code == 200
    assert r.json()["catatan"] == "Screening awal"


def test_min_gt_max_rejected_on_create(client: TestClient) -> None:
    r = client.post(BASE, json={**_payload(), "min_responden": 8, "max_responden": 6})
    assert r.status_code in (400, 422)


def test_not_found(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE}/dses_tidakada")
    assert r.status_code == 404


def test_transition_draft_to_open(client: TestClient, created: dict) -> None:
    r = client.post(f"{BASE}/{created['id']}/buka")
    assert r.status_code == 200
    assert r.json()["status"] == "OPEN"


def test_transition_invalid(client: TestClient, created: dict) -> None:
    r = client.post(f"{BASE}/{created['id']}/tutup")
    assert r.status_code in (400, 422)


def test_full_lifecycle(client: TestClient) -> None:
    sesi = client.post(BASE, json=_payload()).json()
    sesi_id = sesi["id"]
    assert client.post(f"{BASE}/{sesi_id}/buka").json()["status"] == "OPEN"
    assert client.post(f"{BASE}/{sesi_id}/tutup").json()["status"] == "CLOSED"


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
    assert "paksa=true" in r.json()["message"]


def test_delete_non_draft_dengan_paksa_ok(client: TestClient) -> None:
    sesi = client.post(BASE, json=_payload()).json()
    client.post(f"{BASE}/{sesi['id']}/buka")
    r = client.delete(f"{BASE}/{sesi['id']}", params={"paksa": True})
    assert r.status_code == 204
    assert client.get(f"{BASE}/{sesi['id']}").status_code == 404


def test_delete_paksa_forbidden_non_admin(client: TestClient, client_as) -> None:
    sesi = client.post(BASE, json=_payload()).json()
    client.post(f"{BASE}/{sesi['id']}/buka")
    non_admin = client_as("partisipan-1", groups=["partisipan"])
    r = non_admin.delete(f"{BASE}/{sesi['id']}", params={"paksa": True})
    assert r.status_code == 403


def test_search_by_periode(client: TestClient, created: dict) -> None:
    r = client.post(
        f"{BASE}/search",
        json={"domain": [["periode", "=", created["periode"]]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1
