"""Test kunci optimistik (If-Match/ETag), Idempotency-Key, dan skema ketat rute tulis WCP/DCS."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.dcs.schemas.subskala import DcsItemUpdate
from anjab_abk_backend.dcs.seed import ITEM as DCS_ITEM
from anjab_abk_backend.errors import PreconditionFailedError, PreconditionRequiredError
from anjab_abk_backend.etag import check_if_match, compute_etag
from anjab_abk_backend.services.idempotency_sql import SqlIdempotencyStore
from anjab_abk_backend.wcp.schemas.dimensi import WcpItemUpdate

# (modul, base master item, grup untuk daftar item, item_id contoh)
MODUL = ["wcp", "dcs"]
MASTER = {"wcp": "/api/v1/wcp/dimensi", "dcs": "/api/v1/dcs/sub-skala"}
GRUP = {"wcp": "SC", "dcs": "DEMAND"}


def _instrumen(modul: str) -> str:
    return f"/api/v1/{modul}/instrumen"


def _rsp(modul: str) -> str:
    return f"/api/v1/{modul}/responden"


def _item_ids(client: TestClient, modul: str) -> list[str]:
    ids: list[str] = []
    for g in client.get(MASTER[modul]).json():
        ids.extend(i["item_id"] for i in client.get(f"{MASTER[modul]}/{g['kode']}/items").json())
    return ids


class _Model(BaseModel):
    a: int


# --- Unit: skema ketat & helper -------------------------------------------------


def test_skema_item_update_menolak_field_asing() -> None:
    with pytest.raises(ValidationError):
        WcpItemUpdate.model_validate({"pernyataan": "x", "foo": 1})
    with pytest.raises(ValidationError):
        DcsItemUpdate.model_validate({"pernyataan": "x", "foo": 1})


def test_check_if_match_semantik() -> None:
    cur = _Model(a=1)
    etag = compute_etag(cur)
    check_if_match(cur, None, required=False)
    check_if_match(cur, "*", required=True)
    check_if_match(cur, f'"nope", {etag}', required=True)
    with pytest.raises(PreconditionRequiredError):
        check_if_match(cur, None, required=True)
    with pytest.raises(PreconditionFailedError):
        check_if_match(cur, '"nope"', required=False)
    with pytest.raises(PreconditionFailedError):
        check_if_match(cur, f"W/{etag}", required=False)


def test_compute_etag_daftar_model() -> None:
    assert compute_etag([_Model(a=1), _Model(a=2)]) != compute_etag([_Model(a=1)])
    assert compute_etag([_Model(a=1)]) == compute_etag([_Model(a=1)])


# --- Integrasi: field asing ------------------------------------------------------


@pytest.mark.parametrize("modul", MODUL)
def test_patch_item_field_asing_422_item_tak_berubah(client: TestClient, modul: str) -> None:
    item_id = _item_ids(client, modul)[0]
    before = client.get(f"{MASTER[modul]}/items/{item_id}").json()
    r = client.patch(f"{MASTER[modul]}/items/{item_id}", json={"pernyataan": "x", "foo": 1})
    assert r.status_code == 422
    assert client.get(f"{MASTER[modul]}/items/{item_id}").json() == before


# --- Integrasi: If-Match pada item ----------------------------------------------


@pytest.mark.parametrize("modul", MODUL)
def test_item_etag_patch_dan_if_match(client: TestClient, modul: str) -> None:
    item_id = _item_ids(client, modul)[0]
    url = f"{MASTER[modul]}/items/{item_id}"
    etag = client.get(url).headers["etag"]

    ok = client.patch(url, json={"pernyataan": "Teks baru"}, headers={"If-Match": etag})
    assert ok.status_code == 200
    assert ok.headers["etag"] and ok.headers["etag"] != etag

    usang = client.patch(url, json={"pernyataan": "Lain"}, headers={"If-Match": etag})
    assert usang.status_code == 412
    assert client.get(url).json()["pernyataan"] == "Teks baru"

    bintang = client.patch(url, json={"pernyataan": "Bintang"}, headers={"If-Match": "*"})
    assert bintang.status_code == 200


@pytest.mark.parametrize("modul", MODUL)
def test_delete_item_if_match_usang_412(client: TestClient, modul: str) -> None:
    item_id = _item_ids(client, modul)[0]
    url = f"{MASTER[modul]}/items/{item_id}"
    etag = client.get(url).headers["etag"]
    client.patch(url, json={"pernyataan": "Berubah"})
    r = client.delete(url, headers={"If-Match": etag})
    assert r.status_code == 412
    assert client.get(url).status_code == 200


@pytest.mark.parametrize("modul", MODUL)
def test_instrumen_patch_if_match(client: TestClient, modul: str) -> None:
    got = client.get(_instrumen(modul))
    etag = got.headers["etag"]
    ok = client.patch(_instrumen(modul), json={"catatan": "A"}, headers={"If-Match": etag})
    assert ok.status_code == 200
    assert ok.headers["etag"] != etag
    r = client.patch(_instrumen(modul), json={"catatan": "B"}, headers={"If-Match": etag})
    assert r.status_code == 412
    assert client.get(_instrumen(modul)).json()["catatan"] == "A"


@pytest.mark.parametrize("modul", MODUL)
def test_require_if_match_true_tanpa_header_428(app, client: TestClient, modul: str) -> None:
    item_id = _item_ids(client, modul)[0]
    app.dependency_overrides[get_settings] = lambda: Settings(
        docs_enabled=True, cors_origins=[], allowed_hosts=["*"], require_if_match=True
    )
    try:
        r1 = client.patch(f"{MASTER[modul]}/items/{item_id}", json={"pernyataan": "x"})
        r2 = client.patch(_instrumen(modul), json={"catatan": "x"})
        r3 = client.delete(f"{MASTER[modul]}/items/{item_id}")
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert (r1.status_code, r2.status_code, r3.status_code) == (428, 428, 428)


# --- Integrasi: jawaban & responden ---------------------------------------------


@pytest.mark.parametrize("modul", MODUL)
def test_put_jawaban_if_match_usang_412(client: TestClient, partisipan_factory, modul: str) -> None:
    par = partisipan_factory(f"{modul}-ifm")
    rsp = client.post(_rsp(modul), json={"partisipan_ids": [par]}).json()["created"][0]
    ids = _item_ids(client, modul)
    url = f"{_rsp(modul)}/{rsp['id']}/jawaban"

    etag0 = client.get(url).headers["etag"]
    r1 = client.put(
        url,
        json={"jawaban": [{"item_id": ids[0], "skor_raw": 3}]},
        headers={"If-Match": etag0},
    )
    assert r1.status_code == 200
    assert r1.headers["etag"] == client.get(url).headers["etag"]

    r2 = client.put(
        url,
        json={"jawaban": [{"item_id": ids[0], "skor_raw": 5}]},
        headers={"If-Match": etag0},
    )
    assert r2.status_code == 412
    assert client.get(url).json()[0]["skor_raw"] == 3


@pytest.mark.parametrize("modul", MODUL)
def test_delete_responden_if_match_usang_412(
    client: TestClient, partisipan_factory, modul: str
) -> None:
    par = partisipan_factory(f"{modul}-del")
    rsp = client.post(_rsp(modul), json={"partisipan_ids": [par]}).json()["created"][0]
    url = f"{_rsp(modul)}/{rsp['id']}"
    etag = client.get(url).headers["etag"]
    assert client.delete(url, headers={"If-Match": '"usang"'}).status_code == 412
    assert client.get(url).status_code == 200
    assert client.delete(url, headers={"If-Match": etag}).status_code == 204


# --- Integrasi: Idempotency-Key -------------------------------------------------


@pytest.mark.parametrize("modul", MODUL)
def test_assign_responden_key_sama_satu_set_penugasan(
    client: TestClient, partisipan_factory, modul: str
) -> None:
    par = partisipan_factory(f"{modul}-idem")
    h = {"Idempotency-Key": f"assign-{modul}-1"}
    r1 = client.post(_rsp(modul), json={"partisipan_ids": [par]}, headers=h)
    r2 = client.post(_rsp(modul), json={"partisipan_ids": [par]}, headers=h)
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r2.json() == r1.json()
    assert len(r1.json()["created"]) == 1
    assert r2.json()["skipped"] == []
    daftar = client.get(_rsp(modul)).json()["items"]
    assert len([i for i in daftar if i["partisipan_id"] == par]) == 1


@pytest.mark.parametrize("modul", MODUL)
def test_assign_tanpa_key_perilaku_lama(client: TestClient, partisipan_factory, modul: str) -> None:
    par = partisipan_factory(f"{modul}-nokey")
    r1 = client.post(_rsp(modul), json={"partisipan_ids": [par]})
    r2 = client.post(_rsp(modul), json={"partisipan_ids": [par]})
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r2.json()["skipped"]


@pytest.mark.parametrize("modul", MODUL)
def test_submit_jawaban_key_sama_sekali_saja(
    client: TestClient, partisipan_factory, modul: str
) -> None:
    par = partisipan_factory(f"{modul}-sub")
    rsp = client.post(_rsp(modul), json={"partisipan_ids": [par]}).json()["created"][0]
    ids = _item_ids(client, modul)
    base = f"{_rsp(modul)}/{rsp['id']}/jawaban"
    assert (
        client.put(base, json={"jawaban": [{"item_id": i, "skor_raw": 3} for i in ids]}).status_code
        == 200
    )
    h = {"Idempotency-Key": f"submit-{modul}-1"}
    r1 = client.post(f"{base}/submit", headers=h)
    r2 = client.post(f"{base}/submit", headers=h)
    assert r1.status_code == 201, r1.text
    assert r2.status_code == 200
    assert r2.json() == r1.json()
    # tanpa key, submit kedua ditolak karena sudah final → bukti replay bukan submit ulang
    assert client.post(f"{base}/submit").status_code == 422


@pytest.mark.parametrize("modul", MODUL)
def test_tutup_instrumen_key_sama_replay(client: TestClient, modul: str) -> None:
    h = {"Idempotency-Key": f"tutup-{modul}-1"}
    r1 = client.post(f"{_instrumen(modul)}/tutup", headers=h)
    r2 = client.post(f"{_instrumen(modul)}/tutup", headers=h)
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.json() == r1.json()
    assert client.post(f"{_instrumen(modul)}/tutup").status_code == 422


@pytest.mark.parametrize("modul", MODUL)
def test_key_sedang_diproses_409(client: TestClient, db_session, modul: str) -> None:
    path = f"{_instrumen(modul)}/tutup"
    assert SqlIdempotencyStore(db_session).reserve(f"POST:{path}:busy-{modul}")
    r = client.post(path, headers={"Idempotency-Key": f"busy-{modul}"})
    assert r.status_code == 409
    assert client.get(_instrumen(modul)).json()["status"] == "OPEN"


def test_dcs_item_ada_di_seed() -> None:
    assert len(DCS_ITEM) == 42
