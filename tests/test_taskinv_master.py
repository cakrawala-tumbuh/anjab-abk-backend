"""Test CRUD + search endpoint TugasPokok, DetilTugas, UraianTugas."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

TP_BASE = "/api/v1/task-inventory/tugas-pokok"
DT_BASE = "/api/v1/task-inventory/detil-tugas"
UT_BASE = "/api/v1/task-inventory/uraian-tugas"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _uniq(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _create_tp(client: TestClient, nama: str | None = None) -> dict:
    payload = {"nama": nama or f"Tugas Pokok {_uniq()}"}
    r = client.post(TP_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_dt(client: TestClient, tugas_pokok_id: str, nama: str | None = None) -> dict:
    payload = {"nama": nama or f"Detil Tugas {_uniq()}", "tugas_pokok_id": tugas_pokok_id}
    r = client.post(DT_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_ut(client: TestClient, detil_tugas_id: str, tugas_pokok_id: str) -> dict:
    kode = f"TI{uuid.uuid4().hex[:8]}"
    payload = {
        "kode": kode,
        "uraian": f"Uraian tugas {kode}",
        "unit": "TK",
        "kategori_jabatan": "Kepala Sekolah",
        "urutan": 1,
        "detil_tugas_id": detil_tugas_id,
        "tugas_pokok_id": tugas_pokok_id,
    }
    r = client.post(UT_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------- #
# TugasPokok
# --------------------------------------------------------------------------- #


def test_tp_list_ok(anon_client: TestClient) -> None:
    r = anon_client.get(TP_BASE)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert body["total"] > 0  # seeded from task_catalog.json


def test_tp_create_and_get(client: TestClient) -> None:
    tp = _create_tp(client)
    assert tp["id"].startswith("tp_")
    assert tp["nama"]
    r = client.get(f"{TP_BASE}/{tp['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == tp["id"]


def test_tp_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(TP_BASE, json={"nama": "Tanpa Auth"})
    assert r.status_code == 401


def test_tp_create_conflict(client: TestClient) -> None:
    nama = f"TP Duplikat {_uniq()}"
    _create_tp(client, nama=nama)
    r = client.post(TP_BASE, json={"nama": nama})
    assert r.status_code == 409


def test_tp_etag_304(client: TestClient) -> None:
    tp = _create_tp(client)
    r1 = client.get(f"{TP_BASE}/{tp['id']}")
    etag = r1.headers.get("etag")
    assert etag
    r2 = client.get(f"{TP_BASE}/{tp['id']}", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_tp_update(client: TestClient) -> None:
    tp = _create_tp(client)
    nama_baru = f"Updated {_uniq()}"
    r = client.patch(f"{TP_BASE}/{tp['id']}", json={"nama": nama_baru})
    assert r.status_code == 200
    assert r.json()["nama"] == nama_baru


def test_tp_delete(client: TestClient) -> None:
    tp = _create_tp(client)
    assert client.delete(f"{TP_BASE}/{tp['id']}").status_code == 204
    assert client.get(f"{TP_BASE}/{tp['id']}").status_code == 404


def test_tp_not_found(anon_client: TestClient) -> None:
    assert anon_client.get(f"{TP_BASE}/tp_tidakada").status_code == 404


def test_tp_search(client: TestClient) -> None:
    tp = _create_tp(client)
    r = client.post(
        f"{TP_BASE}/search",
        json={"domain": [["id", "=", tp["id"]]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == tp["id"]


# --------------------------------------------------------------------------- #
# DetilTugas
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def tp_for_dt(client: TestClient) -> dict:
    return _create_tp(client, nama=f"TP untuk DT {_uniq()}")


def test_dt_list_ok(anon_client: TestClient) -> None:
    r = anon_client.get(DT_BASE)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert body["total"] > 0  # seeded from task_catalog.json


def test_dt_create_and_get(client: TestClient, tp_for_dt: dict) -> None:
    dt = _create_dt(client, tp_for_dt["id"])
    assert dt["id"].startswith("dt_")
    assert dt["tugas_pokok_id"] == tp_for_dt["id"]
    r = client.get(f"{DT_BASE}/{dt['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == dt["id"]


def test_dt_create_requires_auth(anon_client: TestClient, tp_for_dt: dict) -> None:
    r = anon_client.post(DT_BASE, json={"nama": "Tanpa Auth", "tugas_pokok_id": tp_for_dt["id"]})
    assert r.status_code == 401


def test_dt_etag_304(client: TestClient, tp_for_dt: dict) -> None:
    dt = _create_dt(client, tp_for_dt["id"])
    r1 = client.get(f"{DT_BASE}/{dt['id']}")
    etag = r1.headers.get("etag")
    assert etag
    r2 = client.get(f"{DT_BASE}/{dt['id']}", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_dt_update(client: TestClient, tp_for_dt: dict) -> None:
    dt = _create_dt(client, tp_for_dt["id"])
    nama_baru = f"Updated DT {_uniq()}"
    r = client.patch(f"{DT_BASE}/{dt['id']}", json={"nama": nama_baru})
    assert r.status_code == 200
    assert r.json()["nama"] == nama_baru


def test_dt_delete(client: TestClient, tp_for_dt: dict) -> None:
    dt = _create_dt(client, tp_for_dt["id"])
    assert client.delete(f"{DT_BASE}/{dt['id']}").status_code == 204
    assert client.get(f"{DT_BASE}/{dt['id']}").status_code == 404


def test_dt_not_found(anon_client: TestClient) -> None:
    assert anon_client.get(f"{DT_BASE}/dt_tidakada").status_code == 404


def test_dt_search(client: TestClient, tp_for_dt: dict) -> None:
    _create_dt(client, tp_for_dt["id"])
    r = client.post(
        f"{DT_BASE}/search",
        json={"domain": [["tugas_pokok_id", "=", tp_for_dt["id"]]], "limit": 50, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert all(it["tugas_pokok_id"] == tp_for_dt["id"] for it in body["items"])


# --------------------------------------------------------------------------- #
# UraianTugas
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def tp_for_ut(client: TestClient) -> dict:
    return _create_tp(client, nama=f"TP untuk UT {_uniq()}")


@pytest.fixture(scope="module")
def dt_for_ut(client: TestClient, tp_for_ut: dict) -> dict:
    return _create_dt(client, tp_for_ut["id"], nama=f"DT untuk UT {_uniq()}")


def test_ut_list_ok(anon_client: TestClient) -> None:
    r = anon_client.get(UT_BASE)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert body["total"] >= 2738  # seeded from task_catalog.json


def test_ut_create_and_get(client: TestClient, dt_for_ut: dict, tp_for_ut: dict) -> None:
    ut = _create_ut(client, dt_for_ut["id"], tp_for_ut["id"])
    assert ut["id"].startswith("ut_")
    assert ut["detil_tugas_id"] == dt_for_ut["id"]
    assert ut["tugas_pokok_id"] == tp_for_ut["id"]
    r = client.get(f"{UT_BASE}/{ut['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == ut["id"]


def test_ut_create_requires_auth(anon_client: TestClient, dt_for_ut: dict, tp_for_ut: dict) -> None:
    r = anon_client.post(
        UT_BASE,
        json={
            "kode": f"TI{_uniq()}",
            "uraian": "Test",
            "unit": "TK",
            "kategori_jabatan": "Kepala Sekolah",
            "urutan": 1,
            "detil_tugas_id": dt_for_ut["id"],
            "tugas_pokok_id": tp_for_ut["id"],
        },
    )
    assert r.status_code == 401


def test_ut_create_conflict(client: TestClient, dt_for_ut: dict, tp_for_ut: dict) -> None:
    ut = _create_ut(client, dt_for_ut["id"], tp_for_ut["id"])
    r = client.post(
        UT_BASE,
        json={
            "kode": ut["kode"],
            "uraian": "Duplikat",
            "unit": "TK",
            "kategori_jabatan": "Kepala Sekolah",
            "urutan": 2,
            "detil_tugas_id": dt_for_ut["id"],
            "tugas_pokok_id": tp_for_ut["id"],
        },
    )
    assert r.status_code == 409


def test_ut_etag_304(client: TestClient, dt_for_ut: dict, tp_for_ut: dict) -> None:
    ut = _create_ut(client, dt_for_ut["id"], tp_for_ut["id"])
    r1 = client.get(f"{UT_BASE}/{ut['id']}")
    etag = r1.headers.get("etag")
    assert etag
    r2 = client.get(f"{UT_BASE}/{ut['id']}", headers={"If-None-Match": etag})
    assert r2.status_code == 304


def test_ut_update(client: TestClient, dt_for_ut: dict, tp_for_ut: dict) -> None:
    ut = _create_ut(client, dt_for_ut["id"], tp_for_ut["id"])
    r = client.patch(f"{UT_BASE}/{ut['id']}", json={"uraian": "Uraian sudah diperbarui"})
    assert r.status_code == 200
    assert r.json()["uraian"] == "Uraian sudah diperbarui"


def test_ut_delete(client: TestClient, dt_for_ut: dict, tp_for_ut: dict) -> None:
    ut = _create_ut(client, dt_for_ut["id"], tp_for_ut["id"])
    assert client.delete(f"{UT_BASE}/{ut['id']}").status_code == 204
    assert client.get(f"{UT_BASE}/{ut['id']}").status_code == 404


def test_ut_not_found(anon_client: TestClient) -> None:
    assert anon_client.get(f"{UT_BASE}/ut_tidakada").status_code == 404


def test_ut_search_by_tugas_pokok(client: TestClient, dt_for_ut: dict, tp_for_ut: dict) -> None:
    ut = _create_ut(client, dt_for_ut["id"], tp_for_ut["id"])
    r = client.post(
        f"{UT_BASE}/search",
        json={"domain": [["tugas_pokok_id", "=", tp_for_ut["id"]]], "limit": 50, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(it["id"] == ut["id"] for it in body["items"])


def test_ut_search_by_detil_tugas(client: TestClient, dt_for_ut: dict, tp_for_ut: dict) -> None:
    ut = _create_ut(client, dt_for_ut["id"], tp_for_ut["id"])
    r = client.post(
        f"{UT_BASE}/search",
        json={"domain": [["detil_tugas_id", "=", dt_for_ut["id"]]], "limit": 50, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(it["id"] == ut["id"] for it in body["items"])


def test_ut_search_by_kode(client: TestClient, dt_for_ut: dict, tp_for_ut: dict) -> None:
    ut = _create_ut(client, dt_for_ut["id"], tp_for_ut["id"])
    r = client.post(
        f"{UT_BASE}/search",
        json={"domain": [["kode", "=", ut["kode"]]], "limit": 10, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == ut["id"]


def test_ut_seeded_data_via_catalog_endpoint(anon_client: TestClient) -> None:
    """Pastikan catalog masih bisa diakses setelah seeding."""
    r = anon_client.get(
        "/api/v1/task-inventory/catalog",
        params={"unit": "TK", "kategori_jabatan": "Kepala Sekolah"},
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    assert all(it["unit"] == "TK" for it in items)
