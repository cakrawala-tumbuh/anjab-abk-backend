"""Test endpoint instrumen singleton DCS: get/update/tutup/buka-ulang."""

from __future__ import annotations

from fastapi.testclient import TestClient

BASE = "/api/v1/dcs/instrumen"


def test_get_instrumen_default_open_tanpa_admin_melakukan_apa_pun(anon_client: TestClient) -> None:
    """DB yang baru dimigrasi harus sudah punya baris instrumen OPEN, tanpa setup apa pun."""
    r = anon_client.get(BASE)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "dcs"
    assert data["status"] == "OPEN"
    assert data["min_responden"] == 6
    assert data["closed_at"] is None


def test_update_min_responden_dan_catatan(client: TestClient) -> None:
    r = client.patch(BASE, json={"min_responden": 8, "catatan": "Studi 2026"})
    assert r.status_code == 200
    data = r.json()
    assert data["min_responden"] == 8
    assert data["catatan"] == "Studi 2026"


def test_update_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.patch(BASE, json={"min_responden": 8})
    assert r.status_code == 401


def test_tutup_lalu_status_closed_dan_closed_at_terisi(client: TestClient) -> None:
    r = client.post(f"{BASE}/tutup")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "CLOSED"
    assert data["closed_at"] is not None


def test_tutup_lagi_ditolak(client: TestClient) -> None:
    client.post(f"{BASE}/tutup")
    r = client.post(f"{BASE}/tutup")
    assert r.status_code == 422


def test_buka_ulang_dari_closed(client: TestClient) -> None:
    client.post(f"{BASE}/tutup")
    r = client.post(f"{BASE}/buka-ulang")
    assert r.status_code == 200
    assert r.json()["status"] == "OPEN"


def test_buka_ulang_dari_open_ditolak(client: TestClient) -> None:
    r = client.post(f"{BASE}/buka-ulang")
    assert r.status_code == 422


def test_tutup_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(f"{BASE}/tutup")
    assert r.status_code == 401


def test_buka_ulang_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(f"{BASE}/buka-ulang")
    assert r.status_code == 401
