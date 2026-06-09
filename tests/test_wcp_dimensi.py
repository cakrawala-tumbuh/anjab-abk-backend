"""Test endpoint master data dimensi WCP."""

from __future__ import annotations

from fastapi.testclient import TestClient

BASE = "/api/v1/wcp/dimensi"


def test_list_dimensi_returns_12(anon_client: TestClient) -> None:
    r = anon_client.get(BASE)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 12


def test_list_dimensi_sorted_by_urutan(anon_client: TestClient) -> None:
    r = anon_client.get(BASE)
    items = r.json()
    urutans = [d["urutan"] for d in items]
    assert urutans == sorted(urutans)


def test_list_dimensi_has_risk_flags(anon_client: TestClient) -> None:
    r = anon_client.get(BASE)
    by_kode = {d["kode"]: d for d in r.json()}
    assert by_kode["CH"]["is_risk"] is True
    assert by_kode["SD"]["is_risk"] is True
    assert by_kode["PI"]["is_risk"] is True
    assert by_kode["SC"]["is_risk"] is False
    assert by_kode["RA"]["is_risk"] is False


def test_get_dimensi_with_items(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE}/SC")
    assert r.status_code == 200
    data = r.json()
    assert data["kode"] == "SC"
    assert len(data["items"]) == 6


def test_get_dimensi_items_have_correct_reverse_types(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE}/SC")
    items = {i["item_id"]: i for i in r.json()["items"]}
    assert items["SC1a"]["reverse_type"] == "R"
    assert items["SC1b"]["reverse_type"] == "NONE"


def test_get_dimensi_risk_has_uf_and_r_star(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE}/CH")
    items = {i["item_id"]: i for i in r.json()["items"]}
    assert items["CH1a"]["reverse_type"] == "UF"
    assert items["CH2a"]["reverse_type"] == "R_STAR"


def test_get_dimensi_not_found(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE}/TIDAKADA")
    assert r.status_code == 404


def test_get_dimensi_case_insensitive(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE}/sc")
    assert r.status_code == 200
    assert r.json()["kode"] == "SC"


def test_list_items_by_dimensi(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE}/TM/items")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 6
    assert all(i["dimensi_kode"] == "TM" for i in items)


def test_total_items_across_all_dimensi(anon_client: TestClient) -> None:
    dimensi = anon_client.get(BASE).json()
    total = 0
    for d in dimensi:
        r = anon_client.get(f"{BASE}/{d['kode']}/items")
        total += len(r.json())
    assert total == 72
