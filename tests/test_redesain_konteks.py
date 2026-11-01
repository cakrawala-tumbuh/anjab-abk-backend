"""Tes katalog konteks redesain + seed 14 konteks (backlog `#50`)."""

from __future__ import annotations

from sqlalchemy import func, select

from anjab_abk_backend.models import RedesainKonteksModel
from anjab_abk_backend.redesain.seed import seed_konteks

URL = "/api/v1/redesain/konteks"


def _payload(kode: str = "K-15", **kw):
    base = {
        "kode": kode,
        "tema": "Tema baru",
        "gelombang": "G3",
        "ruang_dugaan": "r",
        "sumber_draft": "s",
        "batas_pemeriksaan": "b",
    }
    base.update(kw)
    return base


def _count(db_session) -> int:
    return db_session.scalar(select(func.count()).select_from(RedesainKonteksModel))


def test_seed_dua_kali_tepat_14_baris(db_session):
    seed_konteks(db_session)
    assert seed_konteks(db_session) == 0
    assert _count(db_session) == 14
    kodes = set(db_session.scalars(select(RedesainKonteksModel.kode)).all())
    assert kodes == {f"K-{i:02d}" for i in range(1, 15)}


def test_seed_gelombang_k11_dan_k14(client_as, partisipan_factory):
    partisipan_factory("tk-1")
    c = client_as("tk-1", groups=["tim-kajian"])
    r = c.post(f"{URL}/search", json={"domain": [["kode", "in", ["K-11", "K-14"]]]}).json()
    assert {i["kode"]: i["gelombang"] for i in r["items"]} == {
        "K-11": "G2",
        "K-14": "G3 - klarifikasi",
    }


def test_suntingan_tema_tidak_tertimpa_seed_ulang(client_as, partisipan_factory, db_session):
    partisipan_factory("tk-2")
    c = client_as("tk-2", groups=["tim-kajian"])
    k01 = c.post(f"{URL}/search", json={"domain": [["kode", "=", "K-01"]]}).json()["items"][0]
    r = c.patch(f"{URL}/{k01['id']}", json={"tema": "Tema disunting Tim"})
    assert r.status_code == 200
    seed_konteks(db_session)
    assert c.get(f"{URL}/{k01['id']}").json()["tema"] == "Tema disunting Tim"


def test_list_dan_search_g1_empat_baris(client_as, partisipan_factory):
    partisipan_factory("tk-3")
    c = client_as("tk-3", groups=["tim-kajian"])
    assert c.get(URL).status_code == 200
    r = c.post(f"{URL}/search", json={"domain": [["gelombang", "=", "G1"]]}).json()
    assert sorted(i["kode"] for i in r["items"]) == ["K-01", "K-02", "K-03", "K-04"]


def test_create_k15_201_dan_riwayat(client_as, partisipan_factory):
    partisipan_factory("tk-4")
    c = client_as("tk-4", groups=["tim-kajian"])
    r = c.post(URL, json=_payload())
    assert r.status_code == 201
    assert r.json()["aktif"] is True
    rw = c.get("/api/v1/redesain/riwayat", params={"entitas_id": r.json()["id"]}).json()
    assert rw["total"] == 1 and rw["items"][0]["entitas"] == "konteks"


def test_nonaktifkan_lewat_patch(client_as, partisipan_factory):
    partisipan_factory("tk-5")
    c = client_as("tk-5", groups=["tim-kajian"])
    cid = c.post(URL, json=_payload("K-16")).json()["id"]
    assert c.patch(f"{URL}/{cid}", json={"aktif": False}).json()["aktif"] is False


def test_negatif_duplikat_409_gelombang_422_patch_404(client_as, partisipan_factory):
    partisipan_factory("tk-6")
    c = client_as("tk-6", groups=["tim-kajian"])
    assert c.post(URL, json=_payload("K-01")).status_code == 409
    assert c.post(URL, json=_payload("K-17", gelombang="G4")).status_code == 422
    assert c.post(URL, json=_payload("X-1")).status_code == 422
    assert c.patch(f"{URL}/zzz", json={"tema": "x"}).status_code == 404
    assert c.get(f"{URL}/zzz").status_code == 404
    assert c.delete(f"{URL}/zzz").status_code == 405


def test_akses_per_grup(client_as, partisipan_factory):
    partisipan_factory("sp-1")
    assert client_as("sp-1", groups=["sekolah-pengisi"]).get(URL).status_code == 403
    assert client_as("sp-1", groups=["admin"]).get(URL).status_code == 403
    partisipan_factory("tk-7")
    assert client_as("tk-7", groups=["tim-kajian"]).get(URL).status_code == 200
