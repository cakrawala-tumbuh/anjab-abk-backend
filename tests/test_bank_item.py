"""Test integritas bank item WCP/DCS: hash bank, status vs paket R1.1, item kembar."""

from __future__ import annotations

import csv
import hashlib
import random
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from anjab_abk_backend.core.bank_item import PATH_PAKET_DCS, PATH_PAKET_WCP, status_terhadap_paket
from anjab_abk_backend.dcs.bank_item import hitung_item_bank_hash as hash_dcs
from anjab_abk_backend.dcs.seed import ITEM as DCS_ITEM
from anjab_abk_backend.wcp.bank_item import hitung_item_bank_hash as hash_wcp
from anjab_abk_backend.wcp.seed import ITEM as WCP_ITEM

WCP_SHA = "23c7480aaf3263c982724a7ae4182e960d83e4b90c84c6bd076e9e8b5f05b06b"
DCS_SHA = "3b10671e9028505c3ae567fb467dc52156cadb9d8bab92af83e3c39f4a404033"


def _wcp_items() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(
            item_id=i[0], dimensi_kode=i[1], pernyataan=i[4], reverse_type=i[5], urutan=i[6]
        )
        for i in WCP_ITEM
    ]


def _dcs_items() -> list[SimpleNamespace]:
    return [
        SimpleNamespace(item_id=i[0], subskala_kode=i[1], pernyataan=i[3], arah=i[4], urutan=i[5])
        for i in DCS_ITEM
    ]


def _norm(teks: str) -> str:
    return " ".join(teks.split())


def _baca_csv(path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as fh:
        return {r["item_id"]: r["pernyataan"] for r in csv.DictReader(fh)}


# --- Unit: data referensi paket ---


def test_sha256_berkas_referensi_paket_tetap() -> None:
    assert hashlib.sha256(PATH_PAKET_WCP.read_bytes()).hexdigest() == WCP_SHA
    assert hashlib.sha256(PATH_PAKET_DCS.read_bytes()).hexdigest() == DCS_SHA


# --- Unit: hash ---


def test_hash_deterministik_dan_64_hex() -> None:
    items = _wcp_items()
    h = hash_wcp(items)
    assert h == hash_wcp(items)
    assert len(h) == 64
    int(h, 16)


def test_hash_berubah_bila_satu_spasi_berubah() -> None:
    items = _dcs_items()
    h0 = hash_dcs(items)
    items[0].pernyataan = items[0].pernyataan + " "
    assert hash_dcs(items) != h0


def test_hash_tidak_bergantung_urutan_input() -> None:
    items = _wcp_items()
    h0 = hash_wcp(items)
    acak = items[:]
    random.Random(7).shuffle(acak)
    assert acak != items
    assert hash_wcp(acak) == h0


# --- Unit: status terhadap paket ---


def test_status_sama_meski_spasi_ganda() -> None:
    paket = {"X1": _norm("Saya bekerja  dengan baik.")}
    assert status_terhadap_paket("X1", "  Saya bekerja   dengan\tbaik. ", paket) == "SAMA"


def test_status_redaksi_beda_bila_tanda_baca_beda() -> None:
    paket = {"X1": "Saya bekerja dengan baik."}
    assert status_terhadap_paket("X1", "Saya bekerja dengan baik", paket) == "REDAKSI_BEDA"
    assert status_terhadap_paket("X1", "saya bekerja dengan baik.", paket) == "REDAKSI_BEDA"


def test_status_tidak_ada_di_paket() -> None:
    assert status_terhadap_paket("Z9", "apa saja", {"X1": "x"}) == "TIDAK_ADA_DI_PAKET"


# --- Integrasi ---


def _hitungan_independen(seed_items, idx_id: int, idx_teks: int, path) -> tuple[int, int]:
    paket = _baca_csv(path)
    beda = tidak = 0
    for row in seed_items:
        ref = paket.get(row[idx_id])
        if ref is None:
            tidak += 1
        elif _norm(row[idx_teks]) != _norm(ref):
            beda += 1
    return beda, tidak


def test_instrumen_dcs_ringkasan_bank(client: TestClient) -> None:
    data = client.get("/api/v1/dcs/instrumen").json()
    beda, tidak = _hitungan_independen(DCS_ITEM, 0, 3, PATH_PAKET_DCS)
    assert data["jumlah_item"] == 42
    assert data["jumlah_tidak_di_paket"] == 2 == tidak
    assert data["jumlah_redaksi_beda"] == beda
    assert len(data["item_bank_hash"]) == 64
    assert data["item_bank_hash"] == hash_dcs(_dcs_items())


def test_instrumen_wcp_ringkasan_bank(client: TestClient) -> None:
    data = client.get("/api/v1/wcp/instrumen").json()
    beda, tidak = _hitungan_independen(WCP_ITEM, 0, 4, PATH_PAKET_WCP)
    assert data["jumlah_item"] == 72
    assert data["jumlah_tidak_di_paket"] == tidak
    assert data["jumlah_redaksi_beda"] == beda
    assert data["item_bank_hash"] == hash_wcp(_wcp_items())


def test_item_dcs_tidak_ada_di_paket_dan_kembar(client: TestClient) -> None:
    items = {
        i["item_id"]: i
        for sk in client.get("/api/v1/dcs/sub-skala").json()
        for i in client.get(f"/api/v1/dcs/sub-skala/{sk['kode']}").json()["items"]
    }
    assert items["D5b"]["status_paket"] == "TIDAK_ADA_DI_PAKET"
    assert items["S6b"]["status_paket"] == "TIDAK_ADA_DI_PAKET"
    assert items["C8a"]["kembar_dengan"] == "WCP:WP1a"
    assert items["S2a"]["kembar_dengan"] == "WCP:SS1a"
    assert items["D1a"]["kembar_dengan"] is None


def test_item_wcp_kembar(client: TestClient) -> None:
    items = {i["item_id"]: i for i in client.get("/api/v1/wcp/dimensi/WP").json()["items"]}
    assert items["WP1a"]["kembar_dengan"] == "DCS:C8a"
    assert items["WP1a"]["status_paket"] in ("SAMA", "REDAKSI_BEDA")
    ss = {i["item_id"]: i for i in client.get("/api/v1/wcp/dimensi/SS").json()["items"]}
    assert ss["SS1a"]["kembar_dengan"] == "DCS:S2a"


def test_teks_item_tidak_diubah_dan_draft_hash_null(client: TestClient, partisipan_factory) -> None:
    pernyataan_seed = {i[0]: i[3] for i in DCS_ITEM}
    sk = client.get("/api/v1/dcs/sub-skala").json()
    api = {
        i["item_id"]: i["pernyataan"]
        for s in sk
        for i in client.get(f"/api/v1/dcs/sub-skala/{s['kode']}").json()["items"]
    }
    assert api == pernyataan_seed

    par = partisipan_factory("bank-draft")
    rsp = client.post("/api/v1/dcs/responden", json={"partisipan_ids": [par]}).json()["created"][0]
    assert rsp["item_bank_hash"] is None
    client.put(
        f"/api/v1/dcs/responden/{rsp['id']}/jawaban",
        json={"jawaban": [{"item_id": "D1a", "skor_raw": 3}]},
    )
    assert client.get(f"/api/v1/dcs/responden/{rsp['id']}").json()["item_bank_hash"] is None


@pytest.mark.parametrize("modul", ["dcs", "wcp"])
def test_submit_mencatat_hash_bank_instrumen(
    client: TestClient, partisipan_factory, modul: str
) -> None:
    ids = [i[0] for i in (DCS_ITEM if modul == "dcs" else WCP_ITEM)]
    par = partisipan_factory(f"bank-submit-{modul}")
    base = f"/api/v1/{modul}/responden"
    rsp = client.post(base, json={"partisipan_ids": [par]}).json()["created"][0]
    r = client.put(
        f"{base}/{rsp['id']}/jawaban",
        json={"jawaban": [{"item_id": i, "skor_raw": 3} for i in ids]},
    )
    assert r.status_code == 200
    assert client.post(f"{base}/{rsp['id']}/jawaban/submit").status_code == 201
    hash_instrumen = client.get(f"/api/v1/{modul}/instrumen").json()["item_bank_hash"]
    rsp_after = client.get(f"{base}/{rsp['id']}").json()
    assert rsp_after["sudah_submit"] is True
    assert rsp_after["item_bank_hash"] == hash_instrumen
