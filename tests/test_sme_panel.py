"""Test CRUD + anggota endpoint sme_panel."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/sme-panel"
PAR_BASE = "/api/v1/partisipan"


def _jabatan_id() -> str:
    return f"jbt_sme_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def panel(client: TestClient) -> dict:
    jbt_id = _jabatan_id()
    r = client.post(BASE, json={"jabatan_id": jbt_id})
    assert r.status_code == 201
    return r.json()


def _buat_partisipan(
    client: TestClient,
    jabatan_utama_id: str,
    jabatan_tambahan_ids: list[str],
    suffix: str,
) -> str:
    payload = {
        "nama": f"SME Test {suffix}",
        "email": f"sme.{suffix}@test.id",
        "sekolah_id": "skl_sme_test",
        "jabatan_utama_id": jabatan_utama_id,
        "jabatan_tambahan_ids": jabatan_tambahan_ids,
        "masa_kerja_tahun": 3,
    }
    r = client.post(PAR_BASE, json=payload)
    assert r.status_code == 201
    return r.json()["id"]


def test_list_ok(anon_client: TestClient) -> None:
    r = anon_client.get(BASE)
    assert r.status_code == 200
    assert "items" in r.json()


def test_create_and_get(client: TestClient, panel: dict) -> None:
    assert panel["id"].startswith("sme_")
    assert "jabatan_id" in panel
    assert panel["partisipan_ids"] == []
    assert panel["koordinator_id"] is None
    assert panel["aktif"] is True
    r = client.get(f"{BASE}/{panel['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == panel["id"]


def test_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(BASE, json={"jabatan_id": _jabatan_id()})
    assert r.status_code == 401


def test_conflict_same_jabatan(client: TestClient, panel: dict) -> None:
    r = client.post(BASE, json={"jabatan_id": panel["jabatan_id"]})
    assert r.status_code == 409


def test_etag_304(client: TestClient, panel: dict) -> None:
    r1 = client.get(f"{BASE}/{panel['id']}")
    etag = r1.headers.get("etag")
    assert etag
    r2 = client.get(f"{BASE}/{panel['id']}", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_update(client: TestClient, panel: dict) -> None:
    r = client.patch(f"{BASE}/{panel['id']}", json={"aktif": False})
    assert r.status_code == 200
    assert r.json()["aktif"] is False


def test_delete(client: TestClient) -> None:
    r = client.post(BASE, json={"jabatan_id": _jabatan_id()})
    pid = r.json()["id"]
    assert client.delete(f"{BASE}/{pid}").status_code == 204
    assert client.get(f"{BASE}/{pid}").status_code == 404


def test_not_found(anon_client: TestClient) -> None:
    assert anon_client.get(f"{BASE}/sme_tidakada").status_code == 404


def test_search(client: TestClient, panel: dict) -> None:
    r = client.post(
        f"{BASE}/search",
        json={"domain": [["id", "=", panel["id"]]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_search_invalid_field(client: TestClient) -> None:
    r = client.post(
        f"{BASE}/search",
        json={"domain": [["unknown_field", "=", "x"]], "limit": 5, "offset": 0},
    )
    assert r.status_code == 422


def test_add_anggota_via_jabatan_utama(client: TestClient, panel: dict) -> None:
    jbt_id = panel["jabatan_id"]
    par_id = _buat_partisipan(client, jbt_id, [], f"utama_{uuid.uuid4().hex[:6]}")
    r = client.post(f"{BASE}/{panel['id']}/anggota", json={"partisipan_id": par_id})
    assert r.status_code == 200
    assert par_id in r.json()["partisipan_ids"]


def test_add_anggota_via_jabatan_tambahan(client: TestClient, panel: dict) -> None:
    jbt_id = panel["jabatan_id"]
    jbt_utama_lain = _jabatan_id()
    par_id = _buat_partisipan(client, jbt_utama_lain, [jbt_id], f"tambahan_{uuid.uuid4().hex[:6]}")
    r = client.post(f"{BASE}/{panel['id']}/anggota", json={"partisipan_id": par_id})
    assert r.status_code == 200
    assert par_id in r.json()["partisipan_ids"]


def test_add_anggota_jabatan_tidak_sesuai(client: TestClient, panel: dict) -> None:
    jbt_beda = _jabatan_id()
    par_id = _buat_partisipan(client, jbt_beda, [], f"beda_{uuid.uuid4().hex[:6]}")
    r = client.post(f"{BASE}/{panel['id']}/anggota", json={"partisipan_id": par_id})
    assert r.status_code == 422


def test_add_anggota_duplikat(client: TestClient, panel: dict) -> None:
    jbt_id = panel["jabatan_id"]
    par_id = _buat_partisipan(client, jbt_id, [], f"dup_{uuid.uuid4().hex[:6]}")
    client.post(f"{BASE}/{panel['id']}/anggota", json={"partisipan_id": par_id})
    r = client.post(f"{BASE}/{panel['id']}/anggota", json={"partisipan_id": par_id})
    assert r.status_code == 409


def test_remove_anggota(client: TestClient, panel: dict) -> None:
    jbt_id = panel["jabatan_id"]
    par_id = _buat_partisipan(client, jbt_id, [], f"remove_{uuid.uuid4().hex[:6]}")
    client.post(f"{BASE}/{panel['id']}/anggota", json={"partisipan_id": par_id})
    r = client.delete(f"{BASE}/{panel['id']}/anggota/{par_id}")
    assert r.status_code == 200
    assert par_id not in r.json()["partisipan_ids"]


def test_remove_anggota_bukan_anggota(client: TestClient, panel: dict) -> None:
    r = client.delete(f"{BASE}/{panel['id']}/anggota/par_bukan_anggota")
    assert r.status_code == 404


def test_add_anggota_requires_auth(anon_client: TestClient, client: TestClient) -> None:
    r_panel = client.post(BASE, json={"jabatan_id": _jabatan_id()})
    panel_id = r_panel.json()["id"]
    r = anon_client.post(f"{BASE}/{panel_id}/anggota", json={"partisipan_id": "par_x"})
    assert r.status_code == 401


def test_set_koordinator(client: TestClient, panel: dict) -> None:
    jbt_id = panel["jabatan_id"]
    par_id = _buat_partisipan(client, jbt_id, [], f"koord_{uuid.uuid4().hex[:6]}")
    client.post(f"{BASE}/{panel['id']}/anggota", json={"partisipan_id": par_id})
    r = client.patch(f"{BASE}/{panel['id']}", json={"koordinator_id": par_id})
    assert r.status_code == 200
    assert r.json()["koordinator_id"] == par_id


def test_set_koordinator_bukan_anggota(client: TestClient, panel: dict) -> None:
    jbt_id = panel["jabatan_id"]
    par_id = _buat_partisipan(client, jbt_id, [], f"nonmember_{uuid.uuid4().hex[:6]}")
    r = client.patch(f"{BASE}/{panel['id']}", json={"koordinator_id": par_id})
    assert r.status_code == 422


def test_hapus_koordinator(client: TestClient, panel: dict) -> None:
    jbt_id = panel["jabatan_id"]
    par_id = _buat_partisipan(client, jbt_id, [], f"hapuskoord_{uuid.uuid4().hex[:6]}")
    client.post(f"{BASE}/{panel['id']}/anggota", json={"partisipan_id": par_id})
    client.patch(f"{BASE}/{panel['id']}", json={"koordinator_id": par_id})
    r = client.patch(f"{BASE}/{panel['id']}", json={"koordinator_id": None})
    assert r.status_code == 200
    assert r.json()["koordinator_id"] is None


def test_remove_anggota_clears_koordinator(client: TestClient, panel: dict) -> None:
    jbt_id = panel["jabatan_id"]
    par_id = _buat_partisipan(client, jbt_id, [], f"clrkoord_{uuid.uuid4().hex[:6]}")
    client.post(f"{BASE}/{panel['id']}/anggota", json={"partisipan_id": par_id})
    client.patch(f"{BASE}/{panel['id']}", json={"koordinator_id": par_id})
    r_remove = client.delete(f"{BASE}/{panel['id']}/anggota/{par_id}")
    assert r_remove.status_code == 200
    assert r_remove.json()["koordinator_id"] is None
