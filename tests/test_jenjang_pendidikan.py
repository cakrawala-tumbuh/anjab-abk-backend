"""Test CRUD + search endpoint jenjang_pendidikan."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/jenjang-pendidikan"


@pytest.fixture
def created(client: TestClient) -> dict:
    kode = f"TK_{uuid.uuid4().hex[:6].upper()}"
    payload = {"kode": kode, "nama": "Taman Kanak-Kanak Test", "urutan": 1}
    r = client.post(BASE, json=payload)
    assert r.status_code == 201
    return r.json()


def test_list_empty_ok(client: TestClient) -> None:
    r = client.get(BASE)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data and "total" in data


def test_create_and_get(client: TestClient, created: dict) -> None:
    jp_id = created["id"]
    assert jp_id.startswith("jp_")
    r = client.get(f"{BASE}/{jp_id}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(BASE, json={"kode": "ANON", "nama": "Anon"})
    assert r.status_code == 401


def test_etag_conditional_get(client: TestClient, created: dict) -> None:
    jp_id = created["id"]
    r1 = client.get(f"{BASE}/{jp_id}")
    etag = r1.headers.get("etag")
    assert etag
    r2 = client.get(f"{BASE}/{jp_id}", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_update(client: TestClient, created: dict) -> None:
    jp_id = created["id"]
    r = client.patch(f"{BASE}/{jp_id}", json={"nama": "TK Updated"})
    assert r.status_code == 200
    assert r.json()["nama"] == "TK Updated"


def test_update_requires_auth(anon_client: TestClient, created: dict) -> None:
    jp_id = created["id"]
    r = anon_client.patch(f"{BASE}/{jp_id}", json={"nama": "X"})
    assert r.status_code == 401


def test_delete(client: TestClient) -> None:
    r = client.post(BASE, json={"kode": "DEL_JP", "nama": "Hapus"})
    jp_id = r.json()["id"]
    r2 = client.delete(f"{BASE}/{jp_id}")
    assert r2.status_code == 204
    r3 = client.get(f"{BASE}/{jp_id}")
    assert r3.status_code == 404


def test_get_not_found(client: TestClient) -> None:
    r = client.get(f"{BASE}/jp_tidakada")
    assert r.status_code == 404


def test_search(client: TestClient, created: dict) -> None:
    r = client.post(
        f"{BASE}/search",
        json={"domain": [["id", "=", created["id"]]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1


def test_search_invalid_field(client: TestClient) -> None:
    r = client.post(
        f"{BASE}/search",
        json={"domain": [["unknown_field", "=", "x"]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 422


def test_idempotency_replay(client: TestClient) -> None:
    key = "idem-replay-jp"
    payload = {"kode": "JP_IDEM", "nama": "Idem"}
    r1 = client.post(BASE, json=payload, headers={"Idempotency-Key": key})
    assert r1.status_code in (200, 201)
    r2 = client.post(BASE, json=payload, headers={"Idempotency-Key": key})
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
