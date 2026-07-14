"""Test endpoint analisis & hasil DCS (instrumen singleton, tanpa sesi)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from anjab_abk_backend.dcs.seed import ITEM

RSP_BASE = "/api/v1/dcs/responden"
INSTRUMEN_BASE = "/api/v1/dcs/instrumen"
ANALISIS_URL = "/api/v1/dcs/analisis"
HASIL_URL = "/api/v1/dcs/hasil"
WCP_RSP_BASE = "/api/v1/wcp/responden"
WCP_INSTRUMEN_BASE = "/api/v1/wcp/instrumen"

ALL_ITEM_IDS = [item[0] for item in ITEM]


def _all_jawaban(skor: int = 3) -> list[dict]:
    return [{"item_id": iid, "skor_raw": skor} for iid in ALL_ITEM_IDS]


def _assign(client: TestClient, partisipan_ids: list[str]) -> list[dict]:
    r = client.post(RSP_BASE, json={"partisipan_ids": partisipan_ids})
    assert r.status_code == 201, r.text
    return r.json()["created"]


def _submit(client: TestClient, responden_id: str, skor: int = 3) -> None:
    r = client.put(f"{RSP_BASE}/{responden_id}/jawaban", json={"jawaban": _all_jawaban(skor)})
    assert r.status_code == 200
    r2 = client.post(f"{RSP_BASE}/{responden_id}/jawaban/submit")
    assert r2.status_code == 201


def test_hasil_responden(client: TestClient, partisipan_factory) -> None:
    par_id = partisipan_factory("dcs-anls-hr")
    rsp = _assign(client, [par_id])[0]
    _submit(client, rsp["id"])

    r = client.get(f"/api/v1/dcs/hasil-responden/{rsp['id']}")
    assert r.status_code == 200
    data = r.json()
    assert data["responden_id"] == rsp["id"]
    assert len(data["sub_skala"]) == 3
    assert data["risk_flag"] in ("HIGH", "MODERATE", "LOW")
    codes = {s["subskala_kode"] for s in data["sub_skala"]}
    assert codes == {"DEMAND", "CONTROL", "SUPPORT"}


def test_hasil_responden_belum_submit_ditolak(client: TestClient, partisipan_factory) -> None:
    par_id = partisipan_factory("dcs-anls-belum")
    rsp = _assign(client, [par_id])[0]
    r = client.get(f"/api/v1/dcs/hasil-responden/{rsp['id']}")
    assert r.status_code == 422


def test_analisis_requires_min_responden(client: TestClient, partisipan_factory) -> None:
    client.patch(INSTRUMEN_BASE, json={"min_responden": 2})
    par_id = partisipan_factory("dcs-anls-min")
    rsp = _assign(client, [par_id])[0]
    _submit(client, rsp["id"])
    client.post(f"{INSTRUMEN_BASE}/tutup")

    r = client.post(ANALISIS_URL)
    assert r.status_code == 422


def test_analisis_transisi_closed_ke_analyzed(client: TestClient, partisipan_factory) -> None:
    client.patch(INSTRUMEN_BASE, json={"min_responden": 2})
    ids = [partisipan_factory(f"dcs-anls-tr-{i}") for i in range(2)]
    rsps = _assign(client, ids)
    for rsp in rsps:
        _submit(client, rsp["id"])
    client.post(f"{INSTRUMEN_BASE}/tutup")

    r = client.post(ANALISIS_URL)
    assert r.status_code == 200
    assert client.get(INSTRUMEN_BASE).json()["status"] == "ANALYZED"


def test_hasil_requires_analyzed(client: TestClient) -> None:
    r = client.get(HASIL_URL)
    assert r.status_code == 422


def test_analisis_regresi_angka_identik_dengan_formula_lama(
    client: TestClient, partisipan_factory
) -> None:
    """TEST TERPENTING: regresi angka — nilai HARDCODE dihitung tangan dari formula
    (tidak berubah oleh refactor ini). Skor 3 di SEMUA item membuat skor ter-adjust
    SELALU 3.0 (item F: 3 apa adanya; item UF: 6-3=3) — sehingga per sub-skala:
    skor_mean=3.0, skor_std=0.0 (2 responden identik), cronbach_alpha=None (variance
    total = 0, guard div-by-zero). risk_flag: demand 3.0 (<=3.5, tidak high), control
    & support 3.0 (>=2.5, tidak low) → LOW. Tanpa responden WCP submit, k_index None.
    """
    client.patch(INSTRUMEN_BASE, json={"min_responden": 2})
    ids = [partisipan_factory(f"dcs-anls-regresi-{i}") for i in range(2)]
    rsps = _assign(client, ids)
    for rsp in rsps:
        _submit(client, rsp["id"], skor=3)
    client.post(f"{INSTRUMEN_BASE}/tutup")

    r = client.post(ANALISIS_URL)
    assert r.status_code == 200
    data = r.json()

    assert data["n_responden"] == 2
    assert data["risk_flag"] == "LOW"
    assert data["k_index"] is None
    assert data["k_index_wcp_risk"] is None
    assert len(data["sub_skala"]) == 3
    for sk in data["sub_skala"]:
        assert sk["n_responden"] == 2
        assert sk["skor_mean"] == 3.0
        assert sk["skor_std"] == 0.0
        assert sk["cronbach_alpha"] is None

    # GET /hasil setelah ANALYZED harus konsisten dengan hasil POST /analisis.
    r2 = client.get(HASIL_URL)
    assert r2.status_code == 200
    assert r2.json() == data


def test_k_index_terisi_saat_wcp_punya_responden_submit(
    client: TestClient, partisipan_factory
) -> None:
    all_wcp_item_ids: list[str] = []
    r = client.get("/api/v1/wcp/dimensi")
    for dim in r.json():
        r2 = client.get(f"/api/v1/wcp/dimensi/{dim['kode']}/items")
        all_wcp_item_ids.extend(i["item_id"] for i in r2.json())

    wcp_par = partisipan_factory("dcs-kidx-wcp")
    r_wcp = client.post(WCP_RSP_BASE, json={"partisipan_ids": [wcp_par]})
    assert r_wcp.status_code == 201, r_wcp.text
    wcp_rsp = r_wcp.json()["created"][0]
    client.put(
        f"{WCP_RSP_BASE}/{wcp_rsp['id']}/jawaban",
        json={"jawaban": [{"item_id": iid, "skor_raw": 4} for iid in all_wcp_item_ids]},
    )
    client.post(f"{WCP_RSP_BASE}/{wcp_rsp['id']}/jawaban/submit")

    client.patch(INSTRUMEN_BASE, json={"min_responden": 2})
    ids = [partisipan_factory(f"dcs-kidx-{i}") for i in range(2)]
    rsps = _assign(client, ids)
    for rsp in rsps:
        _submit(client, rsp["id"])
    client.post(f"{INSTRUMEN_BASE}/tutup")

    r = client.post(ANALISIS_URL)
    assert r.status_code == 200
    data = r.json()
    assert data["k_index"] is not None
    assert 0.0 <= data["k_index"] <= 1.0
    assert data["k_index_wcp_risk"] is not None
