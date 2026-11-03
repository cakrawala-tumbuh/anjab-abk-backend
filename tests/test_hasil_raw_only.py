"""Gerbang flag ``WCP_DCS_SCORING`` pada analisis/hasil WCP & DCS (mode RAW_ONLY vs SCORED)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from anjab_abk_backend.core.raw_hasil import agregat_raw_per_item

DCS_RSP, DCS_SUB = "/api/v1/dcs/responden", "/api/v1/dcs/sub-skala"
WCP_RSP, WCP_DIM = "/api/v1/wcp/responden", "/api/v1/wcp/dimensi"
KUNCI_SKOR = {"risk_flag", "k_index", "k_index_wcp_risk", "skor_mean", "cronbach_alpha"}


def _item_ids(client: TestClient, base: str) -> list[str]:
    out: list[str] = []
    for grp in client.get(base).json():
        out.extend(i["item_id"] for i in client.get(f"{base}/{grp['kode']}/items").json())
    return out


def _isi(client: TestClient, rsp_base: str, item_base: str, par_id: str, skor: int = 4) -> str:
    rsp_id = client.post(rsp_base, json={"partisipan_ids": [par_id]}).json()["created"][0]["id"]
    ids = _item_ids(client, item_base)
    r = client.put(
        f"{rsp_base}/{rsp_id}/jawaban",
        json={"jawaban": [{"item_id": i, "skor_raw": skor} for i in ids]},
    )
    assert r.status_code == 200, r.text
    assert client.post(f"{rsp_base}/{rsp_id}/jawaban/submit").status_code == 201
    return rsp_id


def _semua_kunci(obj) -> set[str]:
    if isinstance(obj, dict):
        return set(obj) | {k for v in obj.values() for k in _semua_kunci(v)}
    if isinstance(obj, list):
        return {k for v in obj for k in _semua_kunci(v)}
    return set()


def _siapkan(client, partisipan_factory, rsp_base, item_base, inst, prefix, n=2) -> str:
    client.patch(inst, json={"min_responden": n})
    rid = ""
    for i in range(n):
        rid = _isi(client, rsp_base, item_base, partisipan_factory(f"{prefix}-{i}"))
    client.post(f"{inst}/tutup")
    return rid


def test_agregat_raw_tanpa_reverse_dan_frekuensi() -> None:
    raw = [("a", {"X": 1}), ("b", {"X": 2}), ("c", {"X": 5})]
    [it] = agregat_raw_per_item(raw, [("X", "G", 1)])
    assert it.mean_raw == pytest.approx(2.67)
    assert it.frekuensi == {"1": 1, "2": 1, "3": 0, "4": 0, "5": 1}
    assert it.n == 3 and it.n_kosong == 0


def test_agregat_raw_kosong_tidak_jadi_nol() -> None:
    raw = [("a", {"X": 4}), ("b", {})]
    [it] = agregat_raw_per_item(raw, [("X", "G", 1)])
    assert (it.n, it.n_kosong, it.mean_raw, it.sd_raw) == (1, 1, 4.0, None)
    [kosong] = agregat_raw_per_item([("a", {})], [("X", "G", 1)])
    assert kosong.mean_raw is None and kosong.sd_raw is None


def test_dcs_flag_mati_raw_only(client: TestClient, partisipan_factory) -> None:
    _siapkan(client, partisipan_factory, DCS_RSP, DCS_SUB, "/api/v1/dcs/instrumen", "raw-dcs")
    r = client.post("/api/v1/dcs/analisis")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["mode"] == "RAW_ONLY" and data["n_responden"] == 2
    assert not (_semua_kunci(data) & KUNCI_SKOR)
    assert len(data["items"]) == 42
    assert data["items"][0]["frekuensi"]["4"] == 2
    assert client.get("/api/v1/dcs/hasil").json() == data


def test_wcp_flag_mati_raw_only(client: TestClient, partisipan_factory) -> None:
    _siapkan(client, partisipan_factory, WCP_RSP, WCP_DIM, "/api/v1/wcp/instrumen", "raw-wcp")
    data = client.post("/api/v1/wcp/analisis").json()
    assert data["mode"] == "RAW_ONLY"
    assert not (_semua_kunci(data) & (KUNCI_SKOR | {"interpretasi"}))
    assert len(data["items"]) == 72
    assert client.get("/api/v1/wcp/hasil").json() == data


@pytest.mark.parametrize("grup", ["dcs", "wcp"])
def test_hasil_responden_flag_mati_409_admin_dan_pemilik(
    client: TestClient, client_as, partisipan_factory, grup: str
) -> None:
    rsp_base, item_base = (DCS_RSP, DCS_SUB) if grup == "dcs" else (WCP_RSP, WCP_DIM)
    rid = _isi(client, rsp_base, item_base, partisipan_factory(f"raw-own-{grup}"))
    url = f"/api/v1/{grup}/hasil-responden/{rid}"
    for pelaku in (
        client_as("adm-x", groups=["admin"]),
        client_as(f"raw-own-{grup}", groups=["partisipan"]),
    ):
        r = pelaku.get(url)
        assert r.status_code == 409
        assert r.json()["error"] == "scoring_key_not_approved"
    # jawaban raw tetap terbaca oleh pemilik
    assert client_as(f"raw-own-{grup}").get(f"{rsp_base}/{rid}/jawaban").status_code == 200


@pytest.mark.parametrize("grup", ["dcs", "wcp"])
def test_hasil_responden_flag_mati_tanpa_token_tetap_401(anon_client, grup: str) -> None:
    assert anon_client.get(f"/api/v1/{grup}/hasil-responden/x").status_code == 401


def test_dcs_flag_hidup_scored(client: TestClient, partisipan_factory, skor_hidup) -> None:
    _siapkan(client, partisipan_factory, DCS_RSP, DCS_SUB, "/api/v1/dcs/instrumen", "sc-dcs")
    data = client.post("/api/v1/dcs/analisis").json()
    assert data["mode"] == "SCORED"
    assert "risk_flag" in data and "k_index" in data


def test_wcp_flag_hidup_scored(client: TestClient, partisipan_factory, skor_hidup) -> None:
    _siapkan(client, partisipan_factory, WCP_RSP, WCP_DIM, "/api/v1/wcp/instrumen", "sc-wcp")
    data = client.post("/api/v1/wcp/analisis").json()
    assert data["mode"] == "SCORED"
    assert "skor_mean" in data["dimensi"][0] and "interpretasi" in data["dimensi"][0]


@pytest.mark.parametrize("grup", ["dcs", "wcp"])
def test_min_responden_tetap_berlaku_flag_mati(
    client: TestClient, partisipan_factory, grup: str
) -> None:
    rsp_base, item_base = (DCS_RSP, DCS_SUB) if grup == "dcs" else (WCP_RSP, WCP_DIM)
    inst = f"/api/v1/{grup}/instrumen"
    client.patch(inst, json={"min_responden": 2})
    _isi(client, rsp_base, item_base, partisipan_factory(f"min-{grup}"))
    client.post(f"{inst}/tutup")
    assert client.post(f"/api/v1/{grup}/analisis").status_code == 422
