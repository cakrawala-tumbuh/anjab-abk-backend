"""Test endpoint WCP: responden, jawaban, dan hasil (endpoint yang belum tercakup)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

SESI_BASE = "/api/v1/wcp/sesi"
DIM_BASE = "/api/v1/wcp/dimensi"

_ALL_ITEM_IDS: list[str] = []


def _get_all_item_ids(client: TestClient) -> list[str]:
    global _ALL_ITEM_IDS
    if _ALL_ITEM_IDS:
        return _ALL_ITEM_IDS
    for dim in client.get(DIM_BASE).json():
        r = client.get(f"{DIM_BASE}/{dim['kode']}/items")
        _ALL_ITEM_IDS.extend(i["item_id"] for i in r.json())
    return _ALL_ITEM_IDS


def _build_sesi(client: TestClient, min_responden: int = 2, max_responden: int = 4) -> dict:
    sesi = client.post(
        SESI_BASE,
        json={
            "jabatan_id": f"jbt_{uuid.uuid4().hex[:8]}",
            "periode": "2025-10",
            "min_responden": min_responden,
            "max_responden": max_responden,
        },
    ).json()
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    return client.get(f"{SESI_BASE}/{sesi['id']}").json()


def _add_responden(client: TestClient, sesi_id: str, label: str = "Guru") -> dict:
    return client.post(
        f"{SESI_BASE}/{sesi_id}/responden",
        json={"jabatan_label": label},
    ).json()


def _submit(client: TestClient, responden_id: str, skor: int = 4) -> None:
    item_ids = _get_all_item_ids(client)
    r = client.post(
        f"{SESI_BASE}/responden/{responden_id}/jawaban",
        json={"jawaban": [{"item_id": iid, "skor_raw": skor} for iid in item_ids]},
    )
    assert r.status_code == 201


@pytest.fixture
def open_sesi(client: TestClient) -> dict:
    return _build_sesi(client)


@pytest.fixture
def analyzed_sesi(client: TestClient) -> dict:
    sesi = _build_sesi(client)
    sesi_id = sesi["id"]
    for _ in range(2):
        rsp = _add_responden(client, sesi_id)
        _submit(client, rsp["id"])
    client.post(f"{SESI_BASE}/{sesi_id}/tutup")
    client.post(f"{SESI_BASE}/{sesi_id}/analisis")
    return client.get(f"{SESI_BASE}/{sesi_id}").json()


# --- GET /{sesi_id}/responden ---


def test_list_responden_empty(client: TestClient, open_sesi: dict) -> None:
    r = client.get(f"{SESI_BASE}/{open_sesi['id']}/responden")
    assert r.status_code == 200
    assert r.json() == []


def test_list_responden_after_create(client: TestClient, open_sesi: dict) -> None:
    sesi_id = open_sesi["id"]
    _add_responden(client, sesi_id, "Guru A")
    _add_responden(client, sesi_id, "Guru B")
    r = client.get(f"{SESI_BASE}/{sesi_id}/responden")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert all(d["sesi_id"] == sesi_id for d in data)


def test_list_responden_sesi_not_found(anon_client: TestClient) -> None:
    r = anon_client.get(f"{SESI_BASE}/wses_tidakada/responden")
    assert r.status_code == 404


# --- DELETE /responden/{responden_id} ---


def test_delete_responden_not_submitted(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    r = client.delete(f"{SESI_BASE}/responden/{rsp['id']}")
    assert r.status_code == 204
    assert client.get(f"{SESI_BASE}/responden/{rsp['id']}").status_code == 404


def test_delete_responden_after_submit_rejected(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    _submit(client, rsp["id"])
    r = client.delete(f"{SESI_BASE}/responden/{rsp['id']}")
    assert r.status_code in (400, 422)


def test_delete_responden_requires_auth(anon_client: TestClient, client: TestClient) -> None:
    sesi = _build_sesi(client)
    rsp = _add_responden(client, sesi["id"])
    r = anon_client.delete(f"{SESI_BASE}/responden/{rsp['id']}")
    assert r.status_code == 401


def test_delete_responden_not_found(client: TestClient) -> None:
    r = client.delete(f"{SESI_BASE}/responden/wrsp_tidakada")
    assert r.status_code == 404


# --- GET /responden/{responden_id}/jawaban ---


def test_list_jawaban_before_submit(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    r = client.get(f"{SESI_BASE}/responden/{rsp['id']}/jawaban")
    assert r.status_code == 200
    assert r.json() == []


def test_list_jawaban_after_submit(client: TestClient, open_sesi: dict) -> None:
    rsp = _add_responden(client, open_sesi["id"])
    _submit(client, rsp["id"])
    r = client.get(f"{SESI_BASE}/responden/{rsp['id']}/jawaban")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 72
    assert all(j["responden_id"] == rsp["id"] for j in data)
    item_ids = {j["item_id"] for j in data}
    assert item_ids == set(_get_all_item_ids(client))


def test_list_jawaban_responden_not_found(anon_client: TestClient) -> None:
    r = anon_client.get(f"{SESI_BASE}/responden/wrsp_tidakada/jawaban")
    assert r.status_code == 404


# --- GET /{sesi_id}/hasil (sukses) ---


def test_get_hasil_sesi_success(client: TestClient, analyzed_sesi: dict) -> None:
    sesi_id = analyzed_sesi["id"]
    r = client.get(f"{SESI_BASE}/{sesi_id}/hasil")
    assert r.status_code == 200
    data = r.json()
    assert data["sesi_id"] == sesi_id
    assert data["n_responden"] == 2
    assert len(data["dimensi"]) == 12
    assert all(0.0 <= d["skor_mean"] <= 5.0 for d in data["dimensi"])


def test_get_hasil_sesi_not_found(anon_client: TestClient) -> None:
    r = anon_client.get(f"{SESI_BASE}/wses_tidakada/hasil")
    assert r.status_code == 404


def test_get_hasil_sesi_not_analyzed(client: TestClient) -> None:
    sesi = _build_sesi(client)
    r = client.get(f"{SESI_BASE}/{sesi['id']}/hasil")
    assert r.status_code in (400, 422)
