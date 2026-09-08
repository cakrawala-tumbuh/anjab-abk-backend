"""Test CRUD + search endpoint sekolah."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

BASE = "/api/v1/sekolah"


@pytest.fixture
def created(client: TestClient) -> dict:
    npsn = str(uuid.uuid4().int)[:8]
    payload = {
        "nama": f"SD Test {npsn}",
        "npsn": npsn,
        "jenjang_pendidikan_id": "jp_dummy",
        "kota": "Jakarta",
        "provinsi": "DKI Jakarta",
    }
    r = client.post(BASE, json=payload)
    assert r.status_code == 201
    return r.json()


def test_list_ok(client: TestClient) -> None:
    r = client.get(BASE)
    assert r.status_code == 200
    assert "items" in r.json()


def test_create_and_get(client: TestClient, created: dict) -> None:
    skl_id = created["id"]
    assert skl_id.startswith("skl_")
    r = client.get(f"{BASE}/{skl_id}")
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


def test_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(BASE, json={"nama": "X", "jenjang_pendidikan_id": "jp_x"})
    assert r.status_code == 401


def test_etag_304(client: TestClient, created: dict) -> None:
    skl_id = created["id"]
    r1 = client.get(f"{BASE}/{skl_id}")
    etag = r1.headers.get("etag")
    assert etag
    r2 = client.get(f"{BASE}/{skl_id}", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_update(client: TestClient, created: dict) -> None:
    skl_id = created["id"]
    r = client.patch(f"{BASE}/{skl_id}", json={"kota": "Bandung"})
    assert r.status_code == 200
    assert r.json()["kota"] == "Bandung"


def test_delete(client: TestClient) -> None:
    r = client.post(
        BASE,
        json={"nama": "Hapus", "jenjang_pendidikan_id": "jp_x"},
    )
    skl_id = r.json()["id"]
    assert client.delete(f"{BASE}/{skl_id}").status_code == 204
    assert client.get(f"{BASE}/{skl_id}").status_code == 404


def test_not_found(client: TestClient) -> None:
    assert client.get(f"{BASE}/skl_tidakada").status_code == 404


def test_search(client: TestClient, created: dict) -> None:
    r = client.post(
        f"{BASE}/search",
        json={"domain": [["id", "=", created["id"]]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_search_invalid_field(client: TestClient) -> None:
    r = client.post(
        f"{BASE}/search",
        json={"domain": [["unknown", "=", "x"]], "limit": 5, "offset": 0},
    )
    assert r.status_code == 422


def test_create_dengan_cabang_valid_lalu_baca_kembali(client: TestClient) -> None:
    npsn = str(uuid.uuid4().int)[:8]
    r = client.post(
        BASE,
        json={
            "nama": f"SD Cabang {npsn}",
            "npsn": npsn,
            "jenjang_pendidikan_id": "jp_dummy",
            "cabang": "Bandung",
        },
    )
    assert r.status_code == 201
    assert r.json()["cabang"] == "Bandung"
    skl_id = r.json()["id"]
    r2 = client.get(f"{BASE}/{skl_id}")
    assert r2.status_code == 200
    assert r2.json()["cabang"] == "Bandung"


def test_create_cabang_di_luar_enum_422(client: TestClient) -> None:
    r = client.post(
        BASE,
        json={
            "nama": "SD Enum Salah",
            "jenjang_pendidikan_id": "jp_dummy",
            "cabang": "Surabaya",
        },
    )
    assert r.status_code == 422


def test_create_tanpa_cabang_tersimpan_null(client: TestClient, created: dict) -> None:
    assert created["cabang"] is None


def test_patch_cabang_mengubah_nilai_tersimpan(client: TestClient, created: dict) -> None:
    skl_id = created["id"]
    r = client.patch(f"{BASE}/{skl_id}", json={"cabang": "Semarang"})
    assert r.status_code == 200
    assert r.json()["cabang"] == "Semarang"
    r2 = client.get(f"{BASE}/{skl_id}")
    assert r2.json()["cabang"] == "Semarang"


def test_search_domain_cabang_hanya_mengembalikan_yang_cocok(client: TestClient) -> None:
    npsn_a = str(uuid.uuid4().int)[:8]
    npsn_b = str(uuid.uuid4().int)[:8]
    r_bandung = client.post(
        BASE,
        json={
            "nama": f"SD Bandung {npsn_a}",
            "npsn": npsn_a,
            "jenjang_pendidikan_id": "jp_dummy",
            "cabang": "Bandung",
        },
    )
    r_semarang = client.post(
        BASE,
        json={
            "nama": f"SD Semarang {npsn_b}",
            "npsn": npsn_b,
            "jenjang_pendidikan_id": "jp_dummy",
            "cabang": "Semarang",
        },
    )
    assert r_bandung.status_code == 201
    assert r_semarang.status_code == 201
    bandung_id = r_bandung.json()["id"]
    semarang_id = r_semarang.json()["id"]

    r = client.post(
        f"{BASE}/search",
        json={"domain": [["cabang", "=", "Bandung"]], "limit": 50, "offset": 0},
    )
    assert r.status_code == 200
    ids = {item["id"] for item in r.json()["items"]}
    assert bandung_id in ids
    assert semarang_id not in ids
    assert all(item["cabang"] == "Bandung" for item in r.json()["items"])
