"""Test alur lengkap WCP: responden, jawaban, dan analisis."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

SESI_BASE = "/api/v1/wcp/sesi"
RSP_BASE = "/api/v1/wcp/sesi"

ALL_ITEM_IDS: list[str] = []


def _get_all_item_ids(anon_client: TestClient) -> list[str]:
    global ALL_ITEM_IDS
    if ALL_ITEM_IDS:
        return ALL_ITEM_IDS
    r = anon_client.get("/api/v1/wcp/dimensi")
    for dim in r.json():
        r2 = anon_client.get(f"/api/v1/wcp/dimensi/{dim['kode']}/items")
        ALL_ITEM_IDS.extend(i["item_id"] for i in r2.json())
    return ALL_ITEM_IDS


def _make_jawaban(item_ids: list[str], skor: int = 4) -> dict:
    return {"jawaban": [{"item_id": iid, "skor_raw": skor} for iid in item_ids]}


@pytest.fixture
def open_sesi(client: TestClient) -> dict:
    sesi = client.post(
        SESI_BASE,
        json={"periode": "2025-07", "min_responden": 2, "max_responden": 4},
    ).json()
    client.post(f"{SESI_BASE}/{sesi['id']}/buka")
    return client.get(f"{SESI_BASE}/{sesi['id']}").json()


def _save_draft(client: TestClient, responden_id: str, jawaban: dict) -> None:
    r = client.put(f"/api/v1/wcp/sesi/responden/{responden_id}/jawaban", json=jawaban)
    assert r.status_code == 200


def _submit(client: TestClient, responden_id: str) -> None:
    r = client.post(f"/api/v1/wcp/sesi/responden/{responden_id}/jawaban/submit")
    assert r.status_code == 201


def _add_and_submit_responden(
    client: TestClient, anon_client: TestClient, sesi_id: str, skor: int = 4
) -> dict:
    rsp = client.post(
        f"{RSP_BASE}/{sesi_id}/responden",
        json={"jabatan_label": "Guru Test"},
    ).json()
    item_ids = _get_all_item_ids(anon_client)
    _save_draft(client, rsp["id"], _make_jawaban(item_ids, skor))
    _submit(client, rsp["id"])
    return rsp


def test_add_responden_to_open_sesi(
    client: TestClient, anon_client: TestClient, open_sesi: dict
) -> None:
    sesi_id = open_sesi["id"]
    r = client.post(
        f"{RSP_BASE}/{sesi_id}/responden",
        json={"jabatan_label": "Guru Matematika"},
    )
    assert r.status_code == 201
    assert r.json()["sesi_id"] == sesi_id
    assert r.json()["sudah_submit"] is False


def test_cannot_add_responden_to_draft(client: TestClient) -> None:
    sesi = client.post(
        SESI_BASE,
        json={"periode": "2025-08", "min_responden": 2, "max_responden": 4},
    ).json()
    r = client.post(
        f"{RSP_BASE}/{sesi['id']}/responden",
        json={"jabatan_label": "Guru Test"},
    )
    assert r.status_code in (400, 422)


def test_submit_jawaban_marks_submitted(
    client: TestClient, anon_client: TestClient, open_sesi: dict
) -> None:
    sesi_id = open_sesi["id"]
    rsp = client.post(
        f"{RSP_BASE}/{sesi_id}/responden",
        json={"jabatan_label": "Guru IPA"},
    ).json()
    item_ids = _get_all_item_ids(anon_client)
    _save_draft(client, rsp["id"], _make_jawaban(item_ids, 3))
    r = client.post(f"/api/v1/wcp/sesi/responden/{rsp['id']}/jawaban/submit")
    assert r.status_code == 201
    assert len(r.json()) == 72

    rsp_updated = client.get(f"/api/v1/wcp/sesi/responden/{rsp['id']}").json()
    assert rsp_updated["sudah_submit"] is True


def test_cannot_submit_twice(client: TestClient, anon_client: TestClient, open_sesi: dict) -> None:
    sesi_id = open_sesi["id"]
    rsp = client.post(
        f"{RSP_BASE}/{sesi_id}/responden",
        json={"jabatan_label": "Guru PKN"},
    ).json()
    item_ids = _get_all_item_ids(anon_client)
    jawaban = _make_jawaban(item_ids, 4)
    _save_draft(client, rsp["id"], jawaban)
    _submit(client, rsp["id"])
    r = client.post(f"/api/v1/wcp/sesi/responden/{rsp['id']}/jawaban/submit")
    assert r.status_code in (400, 409, 422)


def test_analisis_run_after_closed(
    client: TestClient, anon_client: TestClient, open_sesi: dict
) -> None:
    sesi_id = open_sesi["id"]
    _add_and_submit_responden(client, anon_client, sesi_id, skor=4)
    _add_and_submit_responden(client, anon_client, sesi_id, skor=3)

    client.post(f"{SESI_BASE}/{sesi_id}/tutup")
    r = client.post(f"{SESI_BASE}/{sesi_id}/analisis")
    assert r.status_code == 200
    hasil = r.json()
    assert hasil["sesi_id"] == sesi_id
    assert hasil["n_responden"] == 2
    assert len(hasil["dimensi"]) == 12


def test_analisis_sesi_status_becomes_analyzed(
    client: TestClient, anon_client: TestClient, open_sesi: dict
) -> None:
    sesi_id = open_sesi["id"]
    _add_and_submit_responden(client, anon_client, sesi_id, skor=5)
    _add_and_submit_responden(client, anon_client, sesi_id, skor=5)

    client.post(f"{SESI_BASE}/{sesi_id}/tutup")
    client.post(f"{SESI_BASE}/{sesi_id}/analisis")
    sesi = client.get(f"{SESI_BASE}/{sesi_id}").json()
    assert sesi["status"] == "ANALYZED"


def test_hasil_responden_scoring(
    client: TestClient, anon_client: TestClient, open_sesi: dict
) -> None:
    sesi_id = open_sesi["id"]
    rsp = client.post(
        f"{RSP_BASE}/{sesi_id}/responden",
        json={"jabatan_label": "Guru Seni"},
    ).json()
    item_ids = _get_all_item_ids(anon_client)
    _save_draft(client, rsp["id"], _make_jawaban(item_ids, 4))
    _submit(client, rsp["id"])
    r = client.get(f"/api/v1/wcp/sesi/responden/{rsp['id']}/hasil")
    assert r.status_code == 200
    hasil = r.json()
    assert hasil["responden_id"] == rsp["id"]
    assert len(hasil["dimensi"]) == 12

    by_kode = {d["dimensi_kode"]: d for d in hasil["dimensi"]}
    # Skor raw 4 untuk item non-reverse → skor adjusted = 4.0 → dimensi normal = CUKUP/BAIK
    # Item reverse (R): 6-4=2, jadi campuran. Rata-rata per dimensi bervariasi.
    assert all(0.0 <= d["skor"] <= 5.0 for d in hasil["dimensi"])
    # Dimensi risiko dengan semua skor 4 (UF as-is = 4, R_STAR = 6-4=2)
    assert by_kode["CH"]["is_risk"] is True


def test_get_hasil_sesi_before_analyzed_fails(
    client: TestClient, anon_client: TestClient, open_sesi: dict
) -> None:
    sesi_id = open_sesi["id"]
    client.post(f"{SESI_BASE}/{sesi_id}/tutup")
    r = client.get(f"{SESI_BASE}/{sesi_id}/hasil")
    assert r.status_code in (400, 422)


def test_analisis_fails_below_min_responden(
    client: TestClient, anon_client: TestClient, open_sesi: dict
) -> None:
    sesi_id = open_sesi["id"]
    _add_and_submit_responden(client, anon_client, sesi_id, skor=4)
    # hanya 1 responden, min=2
    client.post(f"{SESI_BASE}/{sesi_id}/tutup")
    r = client.post(f"{SESI_BASE}/{sesi_id}/analisis")
    assert r.status_code in (400, 422)
