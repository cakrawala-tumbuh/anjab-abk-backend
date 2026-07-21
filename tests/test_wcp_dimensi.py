"""Test endpoint master data dimensi WCP."""

from __future__ import annotations

from fastapi.testclient import TestClient

from anjab_abk_backend.config import Settings
from anjab_abk_backend.dependencies import get_token_verifier
from anjab_abk_backend.main import create_app
from anjab_abk_backend.security import Principal

BASE = "/api/v1/wcp/dimensi"


class _NonAdminVerifier:
    def verify(self, token: str) -> Principal:
        return Principal(subject="u", username="u", groups=["partisipan"])


def test_list_dimensi_returns_12(client: TestClient) -> None:
    r = client.get(BASE)
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 12


def test_list_dimensi_sorted_by_urutan(client: TestClient) -> None:
    r = client.get(BASE)
    items = r.json()
    urutans = [d["urutan"] for d in items]
    assert urutans == sorted(urutans)


def test_list_dimensi_has_risk_flags(client: TestClient) -> None:
    r = client.get(BASE)
    by_kode = {d["kode"]: d for d in r.json()}
    assert by_kode["CH"]["is_risk"] is True
    assert by_kode["SD"]["is_risk"] is True
    assert by_kode["PI"]["is_risk"] is True
    assert by_kode["SC"]["is_risk"] is False
    assert by_kode["RA"]["is_risk"] is False


def test_get_dimensi_with_items(client: TestClient) -> None:
    r = client.get(f"{BASE}/SC")
    assert r.status_code == 200
    data = r.json()
    assert data["kode"] == "SC"
    assert len(data["items"]) == 6


def test_get_dimensi_items_have_correct_reverse_types(client: TestClient) -> None:
    r = client.get(f"{BASE}/SC")
    items = {i["item_id"]: i for i in r.json()["items"]}
    assert items["SC1a"]["reverse_type"] == "R"
    assert items["SC1b"]["reverse_type"] == "NONE"


def test_get_dimensi_risk_has_uf_and_r_star(client: TestClient) -> None:
    r = client.get(f"{BASE}/CH")
    items = {i["item_id"]: i for i in r.json()["items"]}
    assert items["CH1a"]["reverse_type"] == "UF"
    assert items["CH2a"]["reverse_type"] == "R_STAR"


def test_get_dimensi_not_found(client: TestClient) -> None:
    r = client.get(f"{BASE}/TIDAKADA")
    assert r.status_code == 404


def test_get_dimensi_case_insensitive(client: TestClient) -> None:
    r = client.get(f"{BASE}/sc")
    assert r.status_code == 200
    assert r.json()["kode"] == "SC"


def test_list_items_by_dimensi(client: TestClient) -> None:
    r = client.get(f"{BASE}/TM/items")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 6
    assert all(i["dimensi_kode"] == "TM" for i in items)


def test_total_items_across_all_dimensi(client: TestClient) -> None:
    dimensi = client.get(BASE).json()
    total = 0
    for d in dimensi:
        r = client.get(f"{BASE}/{d['kode']}/items")
        total += len(r.json())
    assert total == 72


# --- Update item (admin-only) ---


def test_update_item_as_admin(client: TestClient) -> None:
    r = client.patch(
        f"{BASE}/items/TM1a",
        json={"pernyataan": "Teks baru TM1a.", "reverse_type": "NONE", "urutan": 7},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["pernyataan"] == "Teks baru TM1a."
    assert data["reverse_type"] == "NONE"
    assert data["urutan"] == 7


def test_update_item_partial(client: TestClient) -> None:
    before = client.get(f"{BASE}/AS").json()["items"][0]
    item_id = before["item_id"]
    r = client.patch(f"{BASE}/items/{item_id}", json={"pernyataan": "Hanya teks."})
    assert r.status_code == 200
    data = r.json()
    assert data["pernyataan"] == "Hanya teks."
    assert data["reverse_type"] == before["reverse_type"]


def test_update_item_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.patch(f"{BASE}/items/SC1a", json={"pernyataan": "x"})
    assert r.status_code == 401


def test_update_item_forbidden_for_non_admin(settings: Settings) -> None:
    app = create_app(settings=settings)
    app.dependency_overrides[get_token_verifier] = lambda: _NonAdminVerifier()
    with TestClient(app) as c:
        r = c.patch(
            f"{BASE}/items/SC1a",
            headers={"Authorization": "Bearer t"},
            json={"pernyataan": "x"},
        )
    assert r.status_code == 403


def test_update_item_not_found(client: TestClient) -> None:
    r = client.patch(f"{BASE}/items/TIDAKADA", json={"pernyataan": "x"})
    assert r.status_code == 404


def test_update_item_rejects_invalid_reverse_type(client: TestClient) -> None:
    r = client.patch(f"{BASE}/items/SC1b", json={"reverse_type": "INVALID"})
    assert r.status_code == 422


# --- Delete item (admin-only, OPEN-only) ---

INSTRUMEN_BASE = "/api/v1/wcp/instrumen"
RSP_BASE = "/api/v1/wcp/responden"


def test_delete_item_as_admin(client: TestClient) -> None:
    r = client.delete(f"{BASE}/items/SC1a")
    assert r.status_code == 204
    item_ids = [i["item_id"] for i in client.get(f"{BASE}/SC/items").json()]
    assert "SC1a" not in item_ids
    assert len(item_ids) == 5


def test_delete_item_requires_auth(anon_client: TestClient) -> None:
    r = anon_client.delete(f"{BASE}/items/SC1a")
    assert r.status_code == 401


def test_delete_item_forbidden_for_non_admin(settings: Settings) -> None:
    app = create_app(settings=settings)
    app.dependency_overrides[get_token_verifier] = lambda: _NonAdminVerifier()
    with TestClient(app) as c:
        r = c.delete(f"{BASE}/items/SC1a", headers={"Authorization": "Bearer t"})
    assert r.status_code == 403


def test_delete_item_not_found(client: TestClient) -> None:
    r = client.delete(f"{BASE}/items/TIDAKADA")
    assert r.status_code == 404


def test_delete_item_ditolak_saat_instrumen_tidak_open(client: TestClient) -> None:
    client.post(f"{INSTRUMEN_BASE}/tutup")  # OPEN -> CLOSED
    r = client.delete(f"{BASE}/items/SC1a")
    assert r.status_code == 422


def test_delete_last_item_dimensi_ditolak(client: TestClient) -> None:
    item_ids = [i["item_id"] for i in client.get(f"{BASE}/SC/items").json()]
    for iid in item_ids[:-1]:
        assert client.delete(f"{BASE}/items/{iid}").status_code == 204
    r = client.delete(f"{BASE}/items/{item_ids[-1]}")
    assert r.status_code == 422


def test_delete_item_membersihkan_jawaban_yatim(client: TestClient, partisipan_factory) -> None:
    par_id = partisipan_factory("wcp-del-jwb")
    rsp = client.post(RSP_BASE, json={"partisipan_ids": [par_id]}).json()["created"][0]
    client.put(
        f"{RSP_BASE}/{rsp['id']}/jawaban",
        json={"jawaban": [{"item_id": "SC1a", "skor_raw": 4}]},
    )
    assert any(j["item_id"] == "SC1a" for j in client.get(f"{RSP_BASE}/{rsp['id']}/jawaban").json())

    assert client.delete(f"{BASE}/items/SC1a").status_code == 204

    sisa = client.get(f"{RSP_BASE}/{rsp['id']}/jawaban").json()
    assert all(j["item_id"] != "SC1a" for j in sisa)
