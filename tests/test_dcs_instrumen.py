"""Test endpoint instrumen singleton DCS: get/update/tutup/buka-ulang/reset."""

from __future__ import annotations

from fastapi.testclient import TestClient

from anjab_abk_backend.dcs.seed import ITEM

BASE = "/api/v1/dcs/instrumen"
_ALL_ITEM_IDS = [item[0] for item in ITEM]


def test_get_instrumen_default_open_tanpa_admin_melakukan_apa_pun(client: TestClient) -> None:
    """DB yang baru dimigrasi harus sudah punya baris instrumen OPEN, tanpa setup apa pun."""
    r = client.get(BASE)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "dcs"
    assert data["status"] == "OPEN"
    assert data["min_responden"] == 6
    assert data["closed_at"] is None


def test_update_min_responden_dan_catatan(client: TestClient) -> None:
    r = client.patch(BASE, json={"min_responden": 8, "catatan": "Studi 2026"})
    assert r.status_code == 200
    data = r.json()
    assert data["min_responden"] == 8
    assert data["catatan"] == "Studi 2026"


def test_update_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.patch(BASE, json={"min_responden": 8})
    assert r.status_code == 401


def test_tutup_lalu_status_closed_dan_closed_at_terisi(client: TestClient) -> None:
    r = client.post(f"{BASE}/tutup")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "CLOSED"
    assert data["closed_at"] is not None


def test_tutup_lagi_ditolak(client: TestClient) -> None:
    client.post(f"{BASE}/tutup")
    r = client.post(f"{BASE}/tutup")
    assert r.status_code == 422


def test_buka_ulang_dari_closed(client: TestClient) -> None:
    client.post(f"{BASE}/tutup")
    r = client.post(f"{BASE}/buka-ulang")
    assert r.status_code == 200
    assert r.json()["status"] == "OPEN"


def test_buka_ulang_dari_open_ditolak(client: TestClient) -> None:
    r = client.post(f"{BASE}/buka-ulang")
    assert r.status_code == 422


def test_tutup_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(f"{BASE}/tutup")
    assert r.status_code == 401


def test_buka_ulang_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(f"{BASE}/buka-ulang")
    assert r.status_code == 401


def _submit_satu_responden(client: TestClient, partisipan_factory, slug: str) -> str:
    """Assign + submit satu responden DCS; kembalikan `responden_id`."""
    par_id = partisipan_factory(slug)
    r = client.post("/api/v1/dcs/responden", json={"partisipan_ids": [par_id]})
    assert r.status_code == 201, r.text
    rsp_id = r.json()["created"][0]["id"]

    r2 = client.put(
        f"/api/v1/dcs/responden/{rsp_id}/jawaban",
        json={"jawaban": [{"item_id": iid, "skor_raw": 3} for iid in _ALL_ITEM_IDS]},
    )
    assert r2.status_code == 200
    r3 = client.post(f"/api/v1/dcs/responden/{rsp_id}/jawaban/submit")
    assert r3.status_code == 201
    return rsp_id


def test_reset_dari_analyzed_kembali_open_dan_responden_kosong(
    client: TestClient, partisipan_factory
) -> None:
    client.patch(BASE, json={"min_responden": 1})
    _submit_satu_responden(client, partisipan_factory, "dcs-reset-analyzed")
    client.post(f"{BASE}/tutup")
    r_analisis = client.post("/api/v1/dcs/analisis")
    assert r_analisis.status_code == 200
    assert client.get(BASE).json()["status"] == "ANALYZED"

    r = client.post(f"{BASE}/reset")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "OPEN"
    assert data["closed_at"] is None

    r_rsp = client.get("/api/v1/dcs/responden")
    assert r_rsp.status_code == 200
    assert r_rsp.json()["items"] == []


def test_reset_idempoten_dari_open(client: TestClient) -> None:
    r = client.post(f"{BASE}/reset")
    assert r.status_code == 200
    assert r.json()["status"] == "OPEN"


def test_reset_bukan_admin_ditolak(client_as) -> None:
    non_admin = client_as("dcs-reset-nonadmin", groups=["partisipan"])
    r = non_admin.post(f"{BASE}/reset")
    assert r.status_code == 403


def test_reset_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.post(f"{BASE}/reset")
    assert r.status_code == 401


def test_buka_ulang_biasa_tetap_ditolak_dari_analyzed(
    client: TestClient, partisipan_factory
) -> None:
    """`reset` != `buka-ulang`: buka-ulang biasa tetap 422 dari ANALYZED, hanya
    `reset` yang menjadi jalur keluar sah dari status terminal ini."""
    client.patch(BASE, json={"min_responden": 1})
    _submit_satu_responden(client, partisipan_factory, "dcs-reset-vs-bukaulang")
    client.post(f"{BASE}/tutup")
    client.post("/api/v1/dcs/analisis")
    assert client.get(BASE).json()["status"] == "ANALYZED"

    r = client.post(f"{BASE}/buka-ulang")
    assert r.status_code == 422
