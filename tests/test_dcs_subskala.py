"""Test endpoint master data DCS: sub-skala dan item."""

from __future__ import annotations

from fastapi.testclient import TestClient

BASE = "/api/v1/dcs/sub-skala"


def test_list_sub_skala(anon_client: TestClient) -> None:
    r = anon_client.get(BASE)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3
    kode_list = [s["kode"] for s in data]
    assert kode_list == ["DEMAND", "CONTROL", "SUPPORT"]


def test_get_sub_skala_with_items(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE}/DEMAND")
    assert r.status_code == 200
    data = r.json()
    assert data["kode"] == "DEMAND"
    assert len(data["items"]) == 14
    item_ids = [i["item_id"] for i in data["items"]]
    assert "D1a" in item_ids
    assert "D8" in item_ids


def test_get_sub_skala_case_insensitive(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE}/demand")
    assert r.status_code == 200
    assert r.json()["kode"] == "DEMAND"


def test_get_sub_skala_not_found(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE}/TIDAKADA")
    assert r.status_code == 404


def test_sub_skala_items_endpoint(anon_client: TestClient) -> None:
    for kode in ("DEMAND", "CONTROL", "SUPPORT"):
        r = anon_client.get(f"{BASE}/{kode}/items")
        assert r.status_code == 200
        assert len(r.json()) == 14


def test_items_have_correct_fields(anon_client: TestClient) -> None:
    r = anon_client.get(f"{BASE}/DEMAND/items")
    item = r.json()[0]
    assert "item_id" in item
    assert "sub_dimensi" in item
    assert "pernyataan" in item
    assert item["arah"] in ("F", "UF")


def test_total_items_42(anon_client: TestClient) -> None:
    total = sum(
        len(anon_client.get(f"{BASE}/{k}/items").json()) for k in ("DEMAND", "CONTROL", "SUPPORT")
    )
    assert total == 42
