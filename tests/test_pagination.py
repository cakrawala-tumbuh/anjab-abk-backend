"""Kontrak paginasi `Page[T]` untuk endpoint list koleksi anak (backlog #22).

Menguji retrofit endpoint yang dulunya mengembalikan array telanjang menjadi
`Page[T]` = `{items, total, limit, offset}` + header `Link`, dengan query
`limit`/`offset` lewat `pagination_params` yang sudah ada.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

DCS_RSP = "/api/v1/dcs/responden"
CATALOG = "/api/v1/task-inventory/catalog"
TI_SESI = "/api/v1/task-inventory/sesi"


def _assign_dcs(client: TestClient, partisipan_ids: list[str]) -> None:
    r = client.post(DCS_RSP, json={"partisipan_ids": partisipan_ids})
    assert r.status_code == 201, r.text


def test_dcs_responden_page_shape_dan_limit(client: TestClient, partisipan_factory) -> None:
    ids = [partisipan_factory(f"pg-dcs-{i}") for i in range(3)]
    _assign_dcs(client, ids)

    r = client.get(DCS_RSP, params={"limit": 2, "offset": 0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"items", "total", "limit", "offset"}
    assert body["total"] == 3  # jumlah SELURUH baris cocok, bukan panjang halaman
    assert len(body["items"]) == 2
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert "Link" in r.headers


def test_dcs_responden_offset_ambil_baris_berikutnya(
    client: TestClient, partisipan_factory
) -> None:
    ids = [partisipan_factory(f"pg-next-{i}") for i in range(3)]
    _assign_dcs(client, ids)

    hal1 = client.get(DCS_RSP, params={"limit": 2, "offset": 0}).json()
    hal2 = client.get(DCS_RSP, params={"limit": 2, "offset": 2}).json()
    assert hal2["total"] == 3
    assert len(hal2["items"]) == 1
    assert {i["id"] for i in hal2["items"]}.isdisjoint({i["id"] for i in hal1["items"]})


def test_dcs_responden_offset_melampaui_total(client: TestClient, partisipan_factory) -> None:
    ids = [partisipan_factory(f"pg-over-{i}") for i in range(2)]
    _assign_dcs(client, ids)

    r = client.get(DCS_RSP, params={"limit": 10, "offset": 100})
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 2


def test_dcs_responden_limit_di_luar_batas_422(client: TestClient) -> None:
    assert client.get(DCS_RSP, params={"limit": 0}).status_code == 422
    assert client.get(DCS_RSP, params={"limit": 999}).status_code == 422


def test_dcs_responden_tanpa_token_401(anon_client: TestClient) -> None:
    assert anon_client.get(DCS_RSP).status_code == 401


def test_catalog_filter_jabatan_tetap_berlaku_dengan_limit(
    client: TestClient, jabatan_id_tk: str
) -> None:
    r = client.get(CATALOG, params={"jabatan_id": jabatan_id_tk, "unit": "ALL", "limit": 2})
    assert r.status_code == 200
    body = r.json()
    assert len(body["items"]) <= 2
    assert all(it["jabatan_id"] == jabatan_id_tk for it in body["items"])
    assert body["total"] >= len(body["items"])


def test_taskinv_responden_sesi_tidak_dikenal_tetap_404(client: TestClient) -> None:
    r = client.get(f"{TI_SESI}/tises_tidakada/responden")
    assert r.status_code == 404
