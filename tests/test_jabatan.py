"""Test CRUD + search endpoint jabatan."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/jabatan"


@pytest.fixture
def created(client: TestClient) -> dict:
    kode = f"KS_{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "kode": kode,
        "nama": "Kepala Sekolah Test",
        "jenis": "struktural",
        "deskripsi": "Pimpinan satuan pendidikan.",
    }
    r = client.post(BASE, json=payload)
    assert r.status_code == 201
    return r.json()


def test_list_ok(anon_client: TestClient) -> None:
    r = anon_client.get(BASE)
    assert r.status_code == 200
    assert "items" in r.json()


def test_create_and_get(client: TestClient, created: dict) -> None:
    jbt_id = created["id"]
    assert jbt_id.startswith("jbt_")
    r = client.get(f"{BASE}/{jbt_id}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(BASE, json={"kode": "X", "nama": "X", "jenis": "struktural"})
    assert r.status_code == 401


def test_etag_304(client: TestClient, created: dict) -> None:
    jbt_id = created["id"]
    r1 = client.get(f"{BASE}/{jbt_id}")
    etag = r1.headers.get("etag")
    assert etag
    r2 = client.get(f"{BASE}/{jbt_id}", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_update(client: TestClient, created: dict) -> None:
    jbt_id = created["id"]
    r = client.patch(f"{BASE}/{jbt_id}", json={"nama": "Kepala Sekolah Updated"})
    assert r.status_code == 200
    assert r.json()["nama"] == "Kepala Sekolah Updated"


def test_delete(client: TestClient) -> None:
    r = client.post(BASE, json={"kode": "DEL_JBT", "nama": "Hapus", "jenis": "teknisi"})
    jbt_id = r.json()["id"]
    assert client.delete(f"{BASE}/{jbt_id}").status_code == 204
    assert client.get(f"{BASE}/{jbt_id}").status_code == 404


def test_not_found(anon_client: TestClient) -> None:
    assert anon_client.get(f"{BASE}/jbt_tidakada").status_code == 404


def test_search_by_jenis(client: TestClient, created: dict) -> None:
    r = client.post(
        f"{BASE}/search",
        json={"domain": [["id", "=", created["id"]]], "limit": 20, "offset": 0},
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_invalid_jenis(client: TestClient) -> None:
    r = client.post(BASE, json={"kode": "X3", "nama": "X3", "jenis": "TIDAK_ADA"})
    assert r.status_code == 422
