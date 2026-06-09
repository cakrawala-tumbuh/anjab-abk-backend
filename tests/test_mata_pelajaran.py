"""Test CRUD + search endpoint mata_pelajaran."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/mata-pelajaran"


@pytest.fixture
def created(client: TestClient) -> dict:
    kode = f"MTK_{uuid.uuid4().hex[:6].upper()}"
    payload = {"kode": kode, "nama": "Matematika Test", "kelompok": "umum"}
    r = client.post(BASE, json=payload)
    assert r.status_code == 201
    return r.json()


def test_list_ok(anon_client: TestClient) -> None:
    r = anon_client.get(BASE)
    assert r.status_code == 200
    assert "items" in r.json()


def test_create_and_get(client: TestClient, created: dict) -> None:
    mp_id = created["id"]
    assert mp_id.startswith("mp_")
    r = client.get(f"{BASE}/{mp_id}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(BASE, json={"kode": "X", "nama": "X", "kelompok": "umum"})
    assert r.status_code == 401


def test_etag_304(client: TestClient, created: dict) -> None:
    mp_id = created["id"]
    r1 = client.get(f"{BASE}/{mp_id}")
    etag = r1.headers.get("etag")
    assert etag
    r2 = client.get(f"{BASE}/{mp_id}", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_update(client: TestClient, created: dict) -> None:
    mp_id = created["id"]
    r = client.patch(f"{BASE}/{mp_id}", json={"nama": "Matematika Updated"})
    assert r.status_code == 200
    assert r.json()["nama"] == "Matematika Updated"


def test_delete(client: TestClient) -> None:
    r = client.post(BASE, json={"kode": "DEL_MP", "nama": "Hapus", "kelompok": "umum"})
    mp_id = r.json()["id"]
    assert client.delete(f"{BASE}/{mp_id}").status_code == 204
    assert client.get(f"{BASE}/{mp_id}").status_code == 404


def test_not_found(anon_client: TestClient) -> None:
    assert anon_client.get(f"{BASE}/mp_tidakada").status_code == 404


def test_search_by_kelompok(client: TestClient, created: dict) -> None:
    r = client.post(
        f"{BASE}/search",
        json={"domain": [["id", "=", created["id"]]], "limit": 20, "offset": 0},
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_invalid_kelompok(client: TestClient) -> None:
    r = client.post(BASE, json={"kode": "X2", "nama": "X2", "kelompok": "TIDAK_ADA"})
    assert r.status_code == 422
