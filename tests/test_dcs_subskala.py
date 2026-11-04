"""Test endpoint master data DCS: sub-skala dan item."""

from __future__ import annotations

from fastapi.testclient import TestClient

from anjab_abk_backend.config import Settings
from anjab_abk_backend.dependencies import get_token_verifier
from anjab_abk_backend.main import create_app
from anjab_abk_backend.security import Principal

BASE = "/api/v1/dcs/sub-skala"


class _NonAdminVerifier:
    def verify(self, token: str) -> Principal:
        return Principal(subject="u", username="u", groups=["partisipan"])


def test_list_sub_skala(client: TestClient) -> None:
    r = client.get(BASE)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3
    kode_list = [s["kode"] for s in data]
    assert kode_list == ["DEMAND", "CONTROL", "SUPPORT"]


def test_get_sub_skala_with_items(client: TestClient) -> None:
    r = client.get(f"{BASE}/DEMAND")
    assert r.status_code == 200
    data = r.json()
    assert data["kode"] == "DEMAND"
    assert len(data["items"]) == 14
    item_ids = [i["item_id"] for i in data["items"]]
    assert "D1a" in item_ids
    assert "D8" in item_ids


def test_get_sub_skala_case_insensitive(client: TestClient) -> None:
    r = client.get(f"{BASE}/demand")
    assert r.status_code == 200
    assert r.json()["kode"] == "DEMAND"


def test_get_sub_skala_not_found(client: TestClient) -> None:
    r = client.get(f"{BASE}/TIDAKADA")
    assert r.status_code == 404


def test_sub_skala_items_endpoint(client: TestClient) -> None:
    for kode in ("DEMAND", "CONTROL", "SUPPORT"):
        r = client.get(f"{BASE}/{kode}/items")
        assert r.status_code == 200
        assert len(r.json()) == 14


def test_items_have_correct_fields(client: TestClient) -> None:
    r = client.get(f"{BASE}/DEMAND/items")
    item = r.json()[0]
    assert "item_id" in item
    assert "sub_dimensi" in item
    assert "pernyataan" in item
    assert item["arah"] in ("F", "UF")


def test_total_items_42(client: TestClient) -> None:
    total = sum(
        len(client.get(f"{BASE}/{k}/items").json()) for k in ("DEMAND", "CONTROL", "SUPPORT")
    )
    assert total == 42


# --- Update item (admin-only) ---


def test_update_item_as_admin(client: TestClient) -> None:
    r = client.patch(
        f"{BASE}/items/D1a",
        json={"pernyataan": "Teks baru D1a.", "arah": "F", "urutan": 2},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["pernyataan"] == "Teks baru D1a."
    assert data["arah"] == "F"
    assert data["urutan"] == 2


def test_update_item_partial(client: TestClient) -> None:
    before = client.get(f"{BASE}/CONTROL").json()["items"][0]
    item_id = before["item_id"]
    r = client.patch(f"{BASE}/items/{item_id}", json={"pernyataan": "Hanya teks."})
    assert r.status_code == 200
    data = r.json()
    assert data["pernyataan"] == "Hanya teks."
    assert data["arah"] == before["arah"]


def test_update_item_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.patch(f"{BASE}/items/D1a", json={"pernyataan": "x"})
    assert r.status_code == 401


def test_update_item_forbidden_for_non_admin(settings: Settings) -> None:
    app = create_app(settings=settings)
    app.dependency_overrides[get_token_verifier] = lambda: _NonAdminVerifier()
    with TestClient(app) as c:
        r = c.patch(
            f"{BASE}/items/D1a",
            headers={"Authorization": "Bearer t"},
            json={"pernyataan": "x"},
        )
    assert r.status_code == 403


def test_update_item_not_found(client: TestClient) -> None:
    r = client.patch(f"{BASE}/items/TIDAKADA", json={"pernyataan": "x"})
    assert r.status_code == 404


def test_update_item_rejects_invalid_arah(client: TestClient) -> None:
    r = client.patch(f"{BASE}/items/D1a", json={"arah": "X"})
    assert r.status_code == 422


# --- Delete item (admin-only, OPEN-only) ---

INSTRUMEN_BASE = "/api/v1/dcs/instrumen"
RSP_BASE = "/api/v1/dcs/responden"


def test_delete_item_as_admin(client: TestClient) -> None:
    r = client.delete(f"{BASE}/items/D8")
    assert r.status_code == 204
    item_ids = [i["item_id"] for i in client.get(f"{BASE}/DEMAND/items").json()]
    assert "D8" not in item_ids
    assert len(item_ids) == 13


def test_delete_item_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.delete(f"{BASE}/items/D8")
    assert r.status_code == 401


def test_delete_item_forbidden_for_non_admin(settings: Settings) -> None:
    app = create_app(settings=settings)
    app.dependency_overrides[get_token_verifier] = lambda: _NonAdminVerifier()
    with TestClient(app) as c:
        r = c.delete(f"{BASE}/items/D8", headers={"Authorization": "Bearer t"})
    assert r.status_code == 403


def test_delete_item_not_found(client: TestClient) -> None:
    r = client.delete(f"{BASE}/items/TIDAKADA")
    assert r.status_code == 404


def test_delete_item_ditolak_saat_instrumen_tidak_open(client: TestClient) -> None:
    client.post(f"{INSTRUMEN_BASE}/tutup")  # OPEN -> CLOSED
    r = client.delete(f"{BASE}/items/D8")
    assert r.status_code == 422


def test_delete_last_item_subskala_ditolak(client: TestClient) -> None:
    item_ids = [i["item_id"] for i in client.get(f"{BASE}/DEMAND/items").json()]
    # Hapus semua kecuali satu — sisa 1 item, penghapusan berikutnya harus 422.
    for iid in item_ids[:-1]:
        assert client.delete(f"{BASE}/items/{iid}").status_code == 204
    r = client.delete(f"{BASE}/items/{item_ids[-1]}")
    assert r.status_code == 422


def _isi_satu_jawaban(client: TestClient, partisipan_factory, slug: str) -> str:
    par_id = partisipan_factory(slug)
    rsp = client.post(RSP_BASE, json={"partisipan_ids": [par_id]}).json()["created"][0]
    r = client.put(
        f"{RSP_BASE}/{rsp['id']}/jawaban",
        json={"jawaban": [{"item_id": "D8", "skor_raw": 4}]},
    )
    assert r.status_code == 200, r.text
    return rsp["id"]


def test_delete_item_ditolak_409_bila_instrumen_berisi_jawaban(
    client: TestClient, partisipan_factory
) -> None:
    rsp_id = _isi_satu_jawaban(client, partisipan_factory, "dcs-del-jwb")

    r = client.delete(f"{BASE}/items/D8")
    assert r.status_code == 409
    assert r.json()["error"] == "instrument_has_responses"
    assert "1 responden" in r.json()["message"]
    # Item & jawaban tidak berubah.
    assert any(i["item_id"] == "D8" for i in client.get(f"{BASE}/DEMAND/items").json())
    jwb = client.get(f"{RSP_BASE}/{rsp_id}/jawaban").json()
    assert any(j["item_id"] == "D8" for j in jwb)


def test_patch_item_ditolak_409_bila_instrumen_berisi_jawaban(
    client: TestClient, partisipan_factory
) -> None:
    _isi_satu_jawaban(client, partisipan_factory, "dcs-del-jwb-patch")
    sebelum = {i["item_id"]: i for i in client.get(f"{BASE}/DEMAND/items").json()}["D8"]

    r = client.patch(f"{BASE}/items/D8", json={"pernyataan": "Teks baru."})
    assert r.status_code == 409
    assert r.json()["error"] == "instrument_has_responses"
    sesudah = {i["item_id"]: i for i in client.get(f"{BASE}/DEMAND/items").json()}["D8"]
    assert sesudah["pernyataan"] == sebelum["pernyataan"]


def test_detail_sub_skala_etag_item_sama_dengan_header_item(client: TestClient) -> None:
    items = client.get(f"{BASE}/DEMAND").json()["items"]
    assert len(items) == 14
    for it in items:
        r = client.get(f"{BASE}/items/{it['item_id']}")
        assert it["etag"] == r.headers["ETag"]


def test_detail_sub_skala_etag_dipakai_patch_item_200_lalu_usang_412(client: TestClient) -> None:
    item = client.get(f"{BASE}/DEMAND").json()["items"][0]
    url = f"{BASE}/items/{item['item_id']}"
    hdr = {"If-Match": item["etag"]}
    ok = client.patch(url, json={"pernyataan": "Teks etag DCS."}, headers=hdr)
    assert ok.status_code == 200
    usang = client.patch(url, json={"pernyataan": "Lagi."}, headers=hdr)
    assert usang.status_code == 412


def test_header_etag_item_dcs_tanpa_field_etag(client: TestClient) -> None:
    it = client.get(f"{BASE}/DEMAND").json()["items"][0]
    assert "etag" not in client.get(f"{BASE}/items/{it['item_id']}").json()
