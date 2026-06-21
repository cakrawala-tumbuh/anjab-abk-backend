"""Test endpoint TsResponden dalam sesi Time Study."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

BASE_SESI = "/api/v1/time-study/sesi"


def _build_sesi(client: TestClient) -> dict:
    sesi = client.post(
        BASE_SESI,
        json={
            "jabatan_id": f"jbt_{uuid.uuid4().hex[:8]}",
            "periode": "2025-10",
        },
    ).json()
    return sesi


def _add_responden(
    client: TestClient,
    sesi_id: str,
    label: str = "Guru",
    partisipan_id: str | None = None,
) -> dict:
    payload: dict = {"jabatan_label": label}
    if partisipan_id is not None:
        payload["partisipan_id"] = partisipan_id
    r = client.post(f"{BASE_SESI}/{sesi_id}/responden", json=payload)
    return r.json()


@pytest.fixture
def sesi(client: TestClient) -> dict:
    return _build_sesi(client)


def test_list_responden_empty(client: TestClient, sesi: dict) -> None:
    r = client.get(f"{BASE_SESI}/{sesi['id']}/responden")
    assert r.status_code == 200
    assert r.json() == []


def test_list_responden_after_create(client: TestClient, sesi: dict) -> None:
    sesi_id = sesi["id"]
    _add_responden(client, sesi_id, "Guru A")
    _add_responden(client, sesi_id, "Guru B")
    r = client.get(f"{BASE_SESI}/{sesi_id}/responden")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert all(d["sesi_id"] == sesi_id for d in data)


def test_list_responden_sesi_not_found(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE_SESI}/tses_tidakada/responden")
    assert r.status_code == 404


def test_create_responden_requires_auth(anon_client: TestClient, client: TestClient) -> None:
    sesi = _build_sesi(client)
    r = anon_client.post(
        f"{BASE_SESI}/{sesi['id']}/responden",
        json={"jabatan_label": "Guru"},
    )
    assert r.status_code == 401


def test_create_responden_duplicate_partisipan_same_sesi_rejected(
    client: TestClient, sesi: dict
) -> None:
    """Partisipan yang sama tidak boleh menjadi responden TS lebih dari sekali per sesi."""
    par_id = f"par_{uuid.uuid4().hex[:8]}"
    sesi_id = sesi["id"]

    r1 = client.post(
        f"{BASE_SESI}/{sesi_id}/responden",
        json={"jabatan_label": "Guru A", "partisipan_id": par_id},
    )
    assert r1.status_code == 201

    r2 = client.post(
        f"{BASE_SESI}/{sesi_id}/responden",
        json={"jabatan_label": "Guru A lagi", "partisipan_id": par_id},
    )
    assert r2.status_code == 409


def test_create_responden_same_partisipan_different_sesi_ok(client: TestClient) -> None:
    """Partisipan yang sama boleh menjadi responden di sesi TS yang berbeda."""
    par_id = f"par_{uuid.uuid4().hex[:8]}"

    sesi1 = _build_sesi(client)
    r1 = client.post(
        f"{BASE_SESI}/{sesi1['id']}/responden",
        json={"jabatan_label": "Guru Sesi 1", "partisipan_id": par_id},
    )
    assert r1.status_code == 201

    sesi2 = _build_sesi(client)
    r2 = client.post(
        f"{BASE_SESI}/{sesi2['id']}/responden",
        json={"jabatan_label": "Guru Sesi 2", "partisipan_id": par_id},
    )
    assert r2.status_code == 201


def test_delete_responden(client: TestClient, sesi: dict) -> None:
    rsp = _add_responden(client, sesi["id"])
    rsp_id = rsp["id"]
    r = client.delete(f"{BASE_SESI}/{sesi['id']}/responden/{rsp_id}")
    assert r.status_code == 204


def test_delete_responden_requires_auth(anon_client: TestClient, client: TestClient) -> None:
    sesi = _build_sesi(client)
    rsp = _add_responden(client, sesi["id"])
    r = anon_client.delete(f"{BASE_SESI}/{sesi['id']}/responden/{rsp['id']}")
    assert r.status_code == 401


def test_delete_responden_not_found(client: TestClient, sesi: dict) -> None:
    r = client.delete(f"{BASE_SESI}/{sesi['id']}/responden/trsp_tidakada")
    assert r.status_code == 404
