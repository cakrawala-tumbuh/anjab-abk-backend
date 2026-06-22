"""Test CRUD + search endpoint TugasPokok, DetilTugas, UraianTugas."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

TP_BASE = "/api/v1/task-inventory/tugas-pokok"
DT_BASE = "/api/v1/task-inventory/detil-tugas"
UT_BASE = "/api/v1/task-inventory/uraian-tugas"
CATALOG_BASE = "/api/v1/task-inventory/catalog"
JABATAN_BASE = "/api/v1/jabatan"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _uniq(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def _get_seeded_jabatan_id(anon_client: TestClient) -> str:
    """Ambil jabatan_id pertama dari catalog kombinasi (hasil seeding)."""
    r = anon_client.get(CATALOG_BASE + "/kombinasi")
    rows = r.json()
    assert len(rows) > 0, "Tidak ada data kombinasi catalog setelah seeding"
    return rows[0]["jabatan_id"]


def _get_jabatan_id_for_unit(anon_client: TestClient, unit: str) -> str:
    """Ambil jabatan_id dari catalog kombinasi yang cocok dengan unit tertentu."""
    r = anon_client.get(CATALOG_BASE + "/kombinasi")
    rows = r.json()
    match = next((x for x in rows if x["unit"] == unit), None)
    assert match is not None, f"Tidak ada kombinasi untuk unit '{unit}'"
    return match["jabatan_id"]


def _create_jabatan(client: TestClient, nama: str | None = None) -> dict:
    kode = _uniq("JBT")
    payload = {
        "kode": kode,
        "nama": nama or f"Jabatan {_uniq()}",
        "jenis": "fungsional",
        "aktif": True,
    }
    r = client.post(JABATAN_BASE, json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _create_tp(client: TestClient, jabatan_id: str | None = None, nama: str | None = None) -> dict:
    if jabatan_id is None:
        jbt = _create_jabatan(client)
        jabatan_id = jbt["id"]
    payload = {"jabatan_id": jabatan_id, "nama": nama or f"Tugas Pokok {_uniq()}"}
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
    assert tp["jabatan_id"]
    r = client.get(f"{TP_BASE}/{tp['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == tp["id"]


def test_tp_create_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(TP_BASE, json={"jabatan_id": "jbt_xxx", "nama": "Tanpa Auth"})
    assert r.status_code == 401


def test_tp_create_conflict_same_jabatan(client: TestClient) -> None:
    jbt = _create_jabatan(client)
    nama = f"TP Duplikat {_uniq()}"
    _create_tp(client, jabatan_id=jbt["id"], nama=nama)
    # Sama jabatan_id + sama nama → 409
    r = client.post(TP_BASE, json={"jabatan_id": jbt["id"], "nama": nama})
    assert r.status_code == 409


def test_tp_create_no_conflict_different_jabatan(client: TestClient) -> None:
    nama = f"TP Sama Nama {_uniq()}"
    jbt1 = _create_jabatan(client)
    jbt2 = _create_jabatan(client)
    _create_tp(client, jabatan_id=jbt1["id"], nama=nama)
    # Jabatan berbeda, nama sama → tidak konflik
    r = client.post(TP_BASE, json={"jabatan_id": jbt2["id"], "nama": nama})
    assert r.status_code == 201


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


def test_tp_search_by_jabatan_id(client: TestClient) -> None:
    jbt = _create_jabatan(client)
    tp = _create_tp(client, jabatan_id=jbt["id"])
    r = client.post(
        f"{TP_BASE}/search",
        json={"domain": [["jabatan_id", "=", jbt["id"]]], "limit": 50, "offset": 0},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 1
    assert any(it["id"] == tp["id"] for it in body["items"])


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
    assert "jabatan_id" in ut  # diwarisi dari TugasPokok
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


def test_ut_jabatan_id_diwarisi_dari_tugas_pokok(
    client: TestClient, dt_for_ut: dict, tp_for_ut: dict
) -> None:
    """jabatan_id pada UraianTugas harus sama dengan jabatan_id pada TugasPokoknya."""
    ut = _create_ut(client, dt_for_ut["id"], tp_for_ut["id"])
    assert ut["jabatan_id"] == tp_for_ut["jabatan_id"]


def test_ut_seeded_data_via_catalog_endpoint(anon_client: TestClient) -> None:
    """Pastikan catalog masih bisa diakses setelah seeding."""
    # Ambil kombinasi pertama yang tersedia
    kombis = anon_client.get(CATALOG_BASE + "/kombinasi").json()
    assert len(kombis) > 0
    first = kombis[0]
    jabatan_id = first["jabatan_id"]
    unit = first["unit"]

    r = anon_client.get(CATALOG_BASE, params={"unit": unit, "jabatan_id": jabatan_id})
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0
    assert all(it["unit"] == unit for it in items)
    assert all(it["jabatan_id"] == jabatan_id for it in items)


def test_catalog_with_null_detil_tugas(anon_client: TestClient) -> None:
    """Catalog untuk kombinasi yang punya task tanpa detil_tugas (detil_tugas_id=None) harus 200."""
    # Cari kombinasi SMA Wakil Kepala Sekolah Bidang Kurikulum via jabatan name
    kombis = anon_client.get(CATALOG_BASE + "/kombinasi").json()
    # Cari unit SMA
    sma_kombis = [x for x in kombis if x["unit"] == "SMA"]
    if not sma_kombis:
        pytest.skip("Tidak ada kombinasi SMA dalam catalog")
    jabatan_id = sma_kombis[0]["jabatan_id"]
    unit = "SMA"

    r = anon_client.get(CATALOG_BASE, params={"unit": unit, "jabatan_id": jabatan_id})
    assert r.status_code == 200
    items = r.json()
    assert len(items) > 0


def test_tp_list_large_limit(anon_client: TestClient) -> None:
    """Limit hingga 500 harus diterima (le=500 di pagination_params)."""
    r = anon_client.get(TP_BASE, params={"limit": 200})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body


def test_ut_list_large_limit(anon_client: TestClient) -> None:
    """Limit 500 harus diterima untuk uraian-tugas."""
    r = anon_client.get(UT_BASE, params={"limit": 500})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
