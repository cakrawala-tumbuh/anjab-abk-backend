"""Otorisasi object-level (BOLA/IDOR) untuk hasil per individu DCS & WCP.

Backlog 025 — `GET /{dcs,wcp}/hasil-responden/{id}` adalah data paling sensitif di
aplikasi ini (hasil psikososial & beban kerja per orang). Token valid saja TIDAK cukup:
partisipan tidak boleh membaca hasil rekan kerjanya hanya karena dia login. Guard =
admin ATAU partisipan pemilik responden (`authorize_responden_access`).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

DCS_RSP = "/api/v1/dcs/responden"
DCS_SUB = "/api/v1/dcs/sub-skala"
DCS_HASIL_RSP = "/api/v1/dcs/hasil-responden"

WCP_RSP = "/api/v1/wcp/responden"
WCP_DIM = "/api/v1/wcp/dimensi"
WCP_HASIL_RSP = "/api/v1/wcp/hasil-responden"


def _item_ids(client: TestClient, base: str) -> list[str]:
    out: list[str] = []
    for grp in client.get(base).json():
        r = client.get(f"{base}/{grp['kode']}/items")
        out.extend(i["item_id"] for i in r.json())
    return out


def _assign_and_submit(client: TestClient, rsp_base: str, item_base: str, par_id: str) -> str:
    r = client.post(rsp_base, json={"partisipan_ids": [par_id]})
    assert r.status_code == 201, r.text
    rsp_id = r.json()["created"][0]["id"]

    item_ids = _item_ids(client, item_base)
    r2 = client.put(
        f"{rsp_base}/{rsp_id}/jawaban",
        json={"jawaban": [{"item_id": iid, "skor_raw": 4} for iid in item_ids]},
    )
    assert r2.status_code == 200, r2.text
    r3 = client.post(f"{rsp_base}/{rsp_id}/jawaban/submit")
    assert r3.status_code == 201, r3.text
    return rsp_id


@pytest.mark.parametrize(
    ("rsp_base", "item_base", "hasil_base", "subj"),
    [
        (DCS_RSP, DCS_SUB, DCS_HASIL_RSP, "dcs-hr"),
        (WCP_RSP, WCP_DIM, WCP_HASIL_RSP, "wcp-hr"),
    ],
    ids=["dcs", "wcp"],
)
def test_hasil_responden_partisipan_lain_403(
    client: TestClient,
    client_as,
    partisipan_factory,
    rsp_base: str,
    item_base: str,
    hasil_base: str,
    subj: str,
) -> None:
    """Partisipan B (login, token sah) TIDAK boleh membaca hasil milik partisipan A."""
    par_a = partisipan_factory(f"{subj}-a")
    partisipan_factory(f"{subj}-b")
    rsp_id = _assign_and_submit(client, rsp_base, item_base, par_a)

    as_b = client_as(f"{subj}-b", groups=["partisipan"])
    r = as_b.get(f"{hasil_base}/{rsp_id}")
    assert r.status_code == 403, r.text
    # Isi hasil tidak boleh ikut terkirim bersama respons penolakan.
    assert "dimensi" not in r.json().get("data", {})
    assert "sub_skala" not in r.json().get("data", {})


@pytest.mark.parametrize(
    ("rsp_base", "item_base", "hasil_base", "subj"),
    [
        (DCS_RSP, DCS_SUB, DCS_HASIL_RSP, "dcs-hro"),
        (WCP_RSP, WCP_DIM, WCP_HASIL_RSP, "wcp-hro"),
    ],
    ids=["dcs", "wcp"],
)
def test_hasil_responden_pemilik_boleh(
    client: TestClient,
    client_as,
    partisipan_factory,
    rsp_base: str,
    item_base: str,
    hasil_base: str,
    subj: str,
) -> None:
    """Pemilik responden tetap boleh membaca hasilnya sendiri (tidak over-block)."""
    par_a = partisipan_factory(f"{subj}-a")
    rsp_id = _assign_and_submit(client, rsp_base, item_base, par_a)

    as_a = client_as(f"{subj}-a", groups=["partisipan"])
    r = as_a.get(f"{hasil_base}/{rsp_id}")
    assert r.status_code == 200, r.text
    assert r.json()["responden_id"] == rsp_id


@pytest.mark.parametrize(
    ("rsp_base", "item_base", "hasil_base", "subj"),
    [
        (DCS_RSP, DCS_SUB, DCS_HASIL_RSP, "dcs-hra"),
        (WCP_RSP, WCP_DIM, WCP_HASIL_RSP, "wcp-hra"),
    ],
    ids=["dcs", "wcp"],
)
def test_hasil_responden_admin_boleh(
    client: TestClient,
    client_as,
    partisipan_factory,
    rsp_base: str,
    item_base: str,
    hasil_base: str,
    subj: str,
) -> None:
    """Admin boleh membaca hasil responden mana pun."""
    par_a = partisipan_factory(f"{subj}-a")
    rsp_id = _assign_and_submit(client, rsp_base, item_base, par_a)

    as_admin = client_as(f"{subj}-adm", groups=["admin"])
    r = as_admin.get(f"{hasil_base}/{rsp_id}")
    assert r.status_code == 200, r.text
    assert r.json()["responden_id"] == rsp_id


@pytest.mark.parametrize("hasil_base", [DCS_HASIL_RSP, WCP_HASIL_RSP], ids=["dcs", "wcp"])
def test_hasil_responden_tanpa_token_401(anon_client: TestClient, hasil_base: str) -> None:
    """Kebocoran nyata di produksi (backlog 025 fakta #6): hasil satu individu dapat
    dibaca TANPA token apa pun."""
    assert anon_client.get(f"{hasil_base}/wrsp_7c0ff89d").status_code == 401
