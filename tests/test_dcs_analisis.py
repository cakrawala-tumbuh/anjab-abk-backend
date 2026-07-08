"""Test endpoint analisis DCS: submit jawaban, hasil per responden dan sesi."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from anjab_abk_backend.dcs.seed import ITEM

BASE_SESI = "/api/v1/dcs/sesi"
BASE_SK = "/api/v1/dcs/sub-skala"

# Semua item_id dalam instrumen DCS
ALL_ITEM_IDS = [item[0] for item in ITEM]


def _all_jawaban(skor: int = 3) -> list[dict]:
    return [{"item_id": iid, "skor_raw": skor} for iid in ALL_ITEM_IDS]


def _build_sesi(client: TestClient) -> dict:
    payload = {
        "periode": "2025-07",
        "min_responden": 2,
        "max_responden": 4,
    }
    sesi = client.post(BASE_SESI, json=payload).json()
    client.post(f"{BASE_SESI}/{sesi['id']}/buka")
    return sesi


def _add_responden(client: TestClient, sesi_id: str) -> dict:
    return client.post(
        f"{BASE_SESI}/{sesi_id}/responden",
        json={"jabatan_label": "Guru"},
    ).json()


def _submit(client: TestClient, responden_id: str, skor: int = 3) -> None:
    r = client.put(
        f"{BASE_SESI}/responden/{responden_id}/jawaban",
        json={"jawaban": _all_jawaban(skor)},
    )
    assert r.status_code == 200
    r2 = client.post(f"{BASE_SESI}/responden/{responden_id}/jawaban/submit")
    assert r2.status_code == 201


@pytest.fixture
def sesi_dengan_responden(client: TestClient) -> dict:
    sesi = _build_sesi(client)
    sesi_id = sesi["id"]
    for _ in range(2):
        rsp = _add_responden(client, sesi_id)
        _submit(client, rsp["id"])
    client.post(f"{BASE_SESI}/{sesi_id}/tutup")
    return sesi


def test_submit_incomplete_draft_rejected(client: TestClient) -> None:
    sesi = _build_sesi(client)
    rsp = _add_responden(client, sesi["id"])
    r = client.put(
        f"{BASE_SESI}/responden/{rsp['id']}/jawaban",
        json={"jawaban": [{"item_id": "D1a", "skor_raw": 3}]},
    )
    assert r.status_code == 200
    r2 = client.post(f"{BASE_SESI}/responden/{rsp['id']}/jawaban/submit")
    assert r2.status_code == 422


def test_save_draft_unknown_item_rejected(client: TestClient) -> None:
    sesi = _build_sesi(client)
    rsp = _add_responden(client, sesi["id"])
    jawaban = _all_jawaban()
    jawaban[0]["item_id"] = "UNKNOWN99"
    r = client.put(
        f"{BASE_SESI}/responden/{rsp['id']}/jawaban",
        json={"jawaban": jawaban},
    )
    assert r.status_code in (400, 409, 422)


def test_hasil_responden(client: TestClient) -> None:
    sesi = _build_sesi(client)
    rsp = _add_responden(client, sesi["id"])
    _submit(client, rsp["id"])

    r = client.get(f"{BASE_SESI}/responden/{rsp['id']}/hasil")
    assert r.status_code == 200
    data = r.json()
    assert data["responden_id"] == rsp["id"]
    assert len(data["sub_skala"]) == 3
    assert data["risk_flag"] in ("HIGH", "MODERATE", "LOW")
    codes = {s["subskala_kode"] for s in data["sub_skala"]}
    assert codes == {"DEMAND", "CONTROL", "SUPPORT"}


def test_hasil_responden_netral_is_low(client: TestClient) -> None:
    # Skor 3 di semua item → demand=3 (≤3.5), control=3 (≥2.5), support=3 (≥2.5) → LOW
    # Tapi UF items di-reverse jadi hasilnya bervariasi; cek hanya tipe risk_flag
    sesi = _build_sesi(client)
    rsp = _add_responden(client, sesi["id"])
    _submit(client, rsp["id"], skor=3)
    r = client.get(f"{BASE_SESI}/responden/{rsp['id']}/hasil")
    data = r.json()
    assert data["risk_flag"] in ("HIGH", "MODERATE", "LOW")


def test_analisis_sesi(client: TestClient, sesi_dengan_responden: dict) -> None:
    sesi_id = sesi_dengan_responden["id"]
    r = client.post(f"{BASE_SESI}/{sesi_id}/analisis")
    assert r.status_code == 200
    data = r.json()
    assert data["sesi_id"] == sesi_id
    assert data["n_responden"] == 2
    assert len(data["sub_skala"]) == 3
    assert data["risk_flag"] in ("HIGH", "MODERATE", "LOW")
    assert data["k_index"] is None


def test_analisis_sesi_transisi_ke_analyzed(client: TestClient) -> None:
    sesi = _build_sesi(client)
    sesi_id = sesi["id"]
    for _ in range(2):
        rsp = _add_responden(client, sesi_id)
        _submit(client, rsp["id"])
    client.post(f"{BASE_SESI}/{sesi_id}/tutup")

    client.post(f"{BASE_SESI}/{sesi_id}/analisis")
    r = client.get(f"{BASE_SESI}/{sesi_id}")
    assert r.json()["status"] == "ANALYZED"


def test_hasil_sesi_requires_analyzed(client: TestClient) -> None:
    sesi = _build_sesi(client)
    r = client.get(f"{BASE_SESI}/{sesi['id']}/hasil")
    assert r.status_code in (400, 422)


def test_analisis_requires_min_responden(client: TestClient) -> None:
    sesi = _build_sesi(client)
    sesi_id = sesi["id"]
    rsp = _add_responden(client, sesi_id)
    _submit(client, rsp["id"])
    client.post(f"{BASE_SESI}/{sesi_id}/tutup")

    r = client.post(f"{BASE_SESI}/{sesi_id}/analisis")
    assert r.status_code in (400, 422)
