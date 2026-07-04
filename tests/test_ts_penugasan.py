"""Test endpoint TsPenugasan: assign partisipan ke Time Study (tanpa sesi)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/time-study/penugasan"


def _payload(partisipan_id: str | None = None, aktif: bool = True) -> dict:
    return {
        "partisipan_id": partisipan_id or f"par_{uuid.uuid4().hex[:8]}",
        "aktif": aktif,
    }


@pytest.fixture
def created(client: TestClient) -> dict:
    r = client.post(BASE, json=_payload())
    assert r.status_code == 201
    return r.json()


def test_list_ok(client: TestClient) -> None:
    r = client.get(BASE)
    assert r.status_code == 200
    assert "items" in r.json()


def test_list_requires_admin(anon_client: TestClient) -> None:
    r = anon_client.get(BASE)
    assert r.status_code == 401


def test_create_and_get(client: TestClient, created: dict) -> None:
    penugasan_id = created["id"]
    assert penugasan_id.startswith("tpn_")
    assert created["aktif"] is True
    r = client.get(f"{BASE}/{penugasan_id}")
    assert r.status_code == 200
    assert r.json()["id"] == penugasan_id


def test_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(BASE, json=_payload())
    assert r.status_code == 401


def test_create_duplicate_partisipan_rejected(client: TestClient) -> None:
    """Satu partisipan hanya boleh punya satu penugasan Time Study."""
    par_id = f"par_{uuid.uuid4().hex[:8]}"
    r1 = client.post(BASE, json=_payload(partisipan_id=par_id))
    assert r1.status_code == 201
    r2 = client.post(BASE, json=_payload(partisipan_id=par_id))
    assert r2.status_code == 409


def test_not_found(client: TestClient) -> None:
    r = client.get(f"{BASE}/tpn_tidakada")
    assert r.status_code == 404


def test_get_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE}/tpn_tidakada")
    assert r.status_code == 401


def test_update_toggle_aktif(client: TestClient, created: dict) -> None:
    r = client.patch(f"{BASE}/{created['id']}", json={"aktif": False})
    assert r.status_code == 200
    assert r.json()["aktif"] is False


def test_update_catatan(client: TestClient, created: dict) -> None:
    r = client.patch(f"{BASE}/{created['id']}", json={"catatan": "Sedang cuti"})
    assert r.status_code == 200
    assert r.json()["catatan"] == "Sedang cuti"


def test_delete(client: TestClient, created: dict) -> None:
    r = client.delete(f"{BASE}/{created['id']}")
    assert r.status_code == 204
    assert client.get(f"{BASE}/{created['id']}").status_code == 404


def test_delete_requires_auth(anon_client: TestClient, created: dict) -> None:
    r = anon_client.delete(f"{BASE}/{created['id']}")
    assert r.status_code == 401


def test_delete_not_found(client: TestClient) -> None:
    r = client.delete(f"{BASE}/tpn_tidakada")
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
# Otorisasi object-level (BOLA/IDOR): partisipan tidak boleh akses penugasan
# Time Study milik partisipan lain lewat penebakan penugasan_id.
# --------------------------------------------------------------------------- #


def test_get_penugasan_forbidden_for_non_owner(
    client: TestClient, client_as, partisipan_factory
) -> None:
    par_a = partisipan_factory("ts-bola-a")
    partisipan_factory("ts-bola-b")
    created = client.post(BASE, json=_payload(partisipan_id=par_a)).json()

    as_b = client_as("ts-bola-b")
    assert as_b.get(f"{BASE}/{created['id']}").status_code == 403

    as_a = client_as("ts-bola-a")
    r = as_a.get(f"{BASE}/{created['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_admin_can_access_any_penugasan(client: TestClient, client_as, partisipan_factory) -> None:
    par_a = partisipan_factory("ts-bola-c")
    created = client.post(BASE, json=_payload(partisipan_id=par_a)).json()

    as_admin = client_as("ts-bola-other-admin", groups=["admin"])
    assert as_admin.get(f"{BASE}/{created['id']}").status_code == 200


def test_create_penugasan_forbidden_for_non_admin(client_as) -> None:
    as_partisipan = client_as("ts-bola-d")
    r = as_partisipan.post(BASE, json=_payload())
    assert r.status_code == 403


def test_update_penugasan_forbidden_for_non_admin(
    client: TestClient, client_as, partisipan_factory
) -> None:
    par_a = partisipan_factory("ts-bola-e")
    created = client.post(BASE, json=_payload(partisipan_id=par_a)).json()

    as_a = client_as("ts-bola-e")
    r = as_a.patch(f"{BASE}/{created['id']}", json={"aktif": False})
    assert r.status_code == 403
