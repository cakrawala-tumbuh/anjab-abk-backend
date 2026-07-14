"""Test alur lengkap WCP: analisis & hasil instrumen singleton (tanpa sesi)."""

from __future__ import annotations

from fastapi.testclient import TestClient

RSP_BASE = "/api/v1/wcp/responden"
INSTRUMEN_BASE = "/api/v1/wcp/instrumen"
ANALISIS_URL = "/api/v1/wcp/analisis"
HASIL_URL = "/api/v1/wcp/hasil"
DIM_BASE = "/api/v1/wcp/dimensi"

ALL_ITEM_IDS: list[str] = []


def _get_all_item_ids(anon_client: TestClient) -> list[str]:
    global ALL_ITEM_IDS
    if ALL_ITEM_IDS:
        return ALL_ITEM_IDS
    r = anon_client.get(DIM_BASE)
    for dim in r.json():
        r2 = anon_client.get(f"{DIM_BASE}/{dim['kode']}/items")
        ALL_ITEM_IDS.extend(i["item_id"] for i in r2.json())
    return ALL_ITEM_IDS


def _assign(client: TestClient, partisipan_ids: list[str]) -> list[dict]:
    r = client.post(RSP_BASE, json={"partisipan_ids": partisipan_ids})
    assert r.status_code == 201, r.text
    return r.json()["created"]


def _submit(client: TestClient, anon_client: TestClient, responden_id: str, skor: int = 4) -> None:
    item_ids = _get_all_item_ids(anon_client)
    r = client.put(
        f"{RSP_BASE}/{responden_id}/jawaban",
        json={"jawaban": [{"item_id": iid, "skor_raw": skor} for iid in item_ids]},
    )
    assert r.status_code == 200
    r2 = client.post(f"{RSP_BASE}/{responden_id}/jawaban/submit")
    assert r2.status_code == 201


def test_hasil_responden_scoring(
    client: TestClient, anon_client: TestClient, partisipan_factory
) -> None:
    par_id = partisipan_factory("wcp-anls-hr")
    rsp = _assign(client, [par_id])[0]
    _submit(client, anon_client, rsp["id"], skor=4)

    r = client.get(f"/api/v1/wcp/hasil-responden/{rsp['id']}")
    assert r.status_code == 200
    hasil = r.json()
    assert hasil["responden_id"] == rsp["id"]
    assert len(hasil["dimensi"]) == 12
    assert all(0.0 <= d["skor"] <= 5.0 for d in hasil["dimensi"])
    by_kode = {d["dimensi_kode"]: d for d in hasil["dimensi"]}
    assert by_kode["CH"]["is_risk"] is True


def test_hasil_responden_belum_submit_ditolak(client: TestClient, partisipan_factory) -> None:
    par_id = partisipan_factory("wcp-anls-belum")
    rsp = _assign(client, [par_id])[0]
    r = client.get(f"/api/v1/wcp/hasil-responden/{rsp['id']}")
    assert r.status_code == 422


def test_analisis_fails_below_min_responden(
    client: TestClient, anon_client: TestClient, partisipan_factory
) -> None:
    client.patch(INSTRUMEN_BASE, json={"min_responden": 2})
    par_id = partisipan_factory("wcp-anls-min")
    rsp = _assign(client, [par_id])[0]
    _submit(client, anon_client, rsp["id"])
    client.post(f"{INSTRUMEN_BASE}/tutup")

    r = client.post(ANALISIS_URL)
    assert r.status_code == 422


def test_analisis_run_after_closed(
    client: TestClient, anon_client: TestClient, partisipan_factory
) -> None:
    client.patch(INSTRUMEN_BASE, json={"min_responden": 2})
    ids = [partisipan_factory(f"wcp-anls-run-{i}") for i in range(2)]
    rsps = _assign(client, ids)
    for i, rsp in enumerate(rsps):
        _submit(client, anon_client, rsp["id"], skor=4 if i == 0 else 3)

    client.post(f"{INSTRUMEN_BASE}/tutup")
    r = client.post(ANALISIS_URL)
    assert r.status_code == 200
    hasil = r.json()
    assert hasil["n_responden"] == 2
    assert len(hasil["dimensi"]) == 12


def test_analisis_transisi_ke_analyzed(
    client: TestClient, anon_client: TestClient, partisipan_factory
) -> None:
    client.patch(INSTRUMEN_BASE, json={"min_responden": 2})
    ids = [partisipan_factory(f"wcp-anls-tr-{i}") for i in range(2)]
    rsps = _assign(client, ids)
    for rsp in rsps:
        _submit(client, anon_client, rsp["id"], skor=5)

    client.post(f"{INSTRUMEN_BASE}/tutup")
    client.post(ANALISIS_URL)
    assert client.get(INSTRUMEN_BASE).json()["status"] == "ANALYZED"


def test_hasil_requires_analyzed(client: TestClient) -> None:
    r = client.get(HASIL_URL)
    assert r.status_code == 422


def test_analisis_regresi_angka_identik_dengan_formula_lama(
    client: TestClient, anon_client: TestClient, partisipan_factory
) -> None:
    """TEST TERPENTING: regresi angka — nilai HARDCODE dihitung tangan dari formula
    (tidak berubah oleh refactor ini). Skor 3 di semua item non-reverse tetap 3.0;
    item reverse (R/R_STAR): 6-3=3.0 juga — sehingga SEMUA item ter-adjust menjadi
    3.0 untuk kedua responden, identik. skor_mean=3.0, skor_std=0.0,
    cronbach_alpha=None (variance total = 0) untuk SETIAP dimensi.
    """
    client.patch(INSTRUMEN_BASE, json={"min_responden": 2})
    ids = [partisipan_factory(f"wcp-anls-regresi-{i}") for i in range(2)]
    rsps = _assign(client, ids)
    for rsp in rsps:
        _submit(client, anon_client, rsp["id"], skor=3)

    client.post(f"{INSTRUMEN_BASE}/tutup")
    r = client.post(ANALISIS_URL)
    assert r.status_code == 200
    data = r.json()

    assert data["n_responden"] == 2
    assert len(data["dimensi"]) == 12
    for dim in data["dimensi"]:
        assert dim["n_responden"] == 2
        assert dim["skor_mean"] == 3.0
        assert dim["skor_std"] == 0.0
        assert dim["cronbach_alpha"] is None

    r2 = client.get(HASIL_URL)
    assert r2.status_code == 200
    assert r2.json() == data
