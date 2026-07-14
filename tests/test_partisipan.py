"""Test CRUD + search endpoint partisipan."""

from __future__ import annotations

from fastapi.testclient import TestClient

BASE = "/api/v1/partisipan"

_PAYLOAD = {
    "nama": "Siti Rahayu, S.Pd.",
    "email": "siti.rahayu@sekolah.id",
    "sekolah_id": "skl_dummy",
    "jabatan_utama_id": "jbt_dummy",
    "jabatan_tambahan_ids": ["jbt_b1", "jbt_b2"],
    "masa_kerja_tahun": 5,
    "masa_kerja_bulan": 3,
    "mata_pelajaran_utama_id": "mp_dummy",
}


def test_list_ok(client: TestClient) -> None:
    r = client.get(BASE)
    assert r.status_code == 200
    assert "items" in r.json()


def test_create_and_get(client: TestClient) -> None:
    r = client.post(BASE, json=_PAYLOAD)
    assert r.status_code == 201
    data = r.json()
    assert data["id"].startswith("par_")
    assert data["jabatan_tambahan_ids"] == ["jbt_b1", "jbt_b2"]
    assert data["masa_kerja_tahun"] == 5
    assert data["masa_kerja_bulan"] == 3
    assert data["mata_pelajaran_utama_id"] == "mp_dummy"

    r2 = client.get(f"{BASE}/{data['id']}")
    assert r2.status_code == 200
    assert r2.json()["id"] == data["id"]


def test_create_menautkan_authentik_user_id_ke_email(client: TestClient) -> None:
    """Tautan identitas: `authentik_user_id` = email (klaim `sub`, sub_mode=user_email)."""
    payload = {**_PAYLOAD, "email": "tautan.subject@ypii.sch.id"}
    r = client.post(BASE, json=payload)
    assert r.status_code == 201
    assert r.json()["authentik_user_id"] == "tautan.subject@ypii.sch.id"


def test_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(BASE, json=_PAYLOAD)
    assert r.status_code == 401


def test_create_tanpa_jabatan_tambahan(client: TestClient) -> None:
    payload = {**_PAYLOAD, "jabatan_tambahan_ids": [], "mata_pelajaran_utama_id": None}
    r = client.post(BASE, json=payload)
    assert r.status_code == 201
    assert r.json()["jabatan_tambahan_ids"] == []
    assert r.json()["mata_pelajaran_utama_id"] is None


def test_etag_304(client: TestClient) -> None:
    r = client.post(BASE, json=_PAYLOAD)
    par_id = r.json()["id"]
    r1 = client.get(f"{BASE}/{par_id}")
    etag = r1.headers.get("etag")
    assert etag
    r2 = client.get(f"{BASE}/{par_id}", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_update(client: TestClient) -> None:
    r = client.post(BASE, json=_PAYLOAD)
    par_id = r.json()["id"]
    r2 = client.patch(f"{BASE}/{par_id}", json={"masa_kerja_tahun": 10, "jabatan_tambahan_ids": []})
    assert r2.status_code == 200
    assert r2.json()["masa_kerja_tahun"] == 10
    assert r2.json()["jabatan_tambahan_ids"] == []


def test_delete(client: TestClient) -> None:
    r = client.post(BASE, json=_PAYLOAD)
    par_id = r.json()["id"]
    assert client.delete(f"{BASE}/{par_id}").status_code == 204
    assert client.get(f"{BASE}/{par_id}").status_code == 404


def test_not_found(client: TestClient) -> None:
    assert client.get(f"{BASE}/par_tidakada").status_code == 404


def test_search(client: TestClient) -> None:
    r = client.post(BASE, json=_PAYLOAD)
    par_id = r.json()["id"]
    r2 = client.post(
        f"{BASE}/search",
        json={"domain": [["id", "=", par_id]], "limit": 10, "offset": 0},
    )
    assert r2.status_code == 200
    assert r2.json()["total"] >= 1


def test_search_invalid_field(client: TestClient) -> None:
    r = client.post(
        f"{BASE}/search",
        json={"domain": [["unknown", "=", "x"]], "limit": 5, "offset": 0},
    )
    assert r.status_code == 422
