"""Tes sesi partisipasi redesain: CRUD+search Tim, rekap menit per orang (backlog `#60`)."""

from __future__ import annotations

from sqlalchemy import select

from anjab_abk_backend.models import RedesainMasalahModel, RedesainRiwayatModel

URL = "/api/v1/redesain/sesi"
URL_KODE = "/api/v1/redesain/kode-orang"


def _masalah_id(db_session, kode: str = "M-K01-01") -> str:
    return db_session.scalars(
        select(RedesainMasalahModel.id).where(RedesainMasalahModel.kode == kode)
    ).one()


def _tim(client_as, partisipan_factory, subject: str):
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _kode(c) -> str:
    r = c.post(URL_KODE, json={"keterangan_peran": "Peserta sesi"})
    assert r.status_code == 201, r.text
    return r.json()["kode"]


def _sesi(kode_sesi: str, kode_orang: str, **kw):
    base = {
        "kode_sesi": kode_sesi,
        "kode_orang": kode_orang,
        "peran": "Wakil kepala sekolah",
        "jenis_kegiatan": "Klarifikasi",
    }
    base.update(kw)
    return base


def _rekap(c, kode: str) -> dict:
    r = c.get(f"{URL}/rekap-orang", params={"limit": 100})
    assert r.status_code == 200, r.text
    return {x["kode_orang"]: x for x in r.json()["items"]}[kode]


def test_rekap_dua_orang_dua_sesi(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "ss-1")
    a, b = _kode(c), _kode(c)
    assert (
        c.post(URL, json=_sesi("S-01", a, menit_rencana=60, menit_disepakati=45)).status_code == 201
    )
    assert c.post(URL, json=_sesi("S-01", b, menit_rencana=60)).status_code == 201
    assert c.post(URL, json=_sesi("S-02", a, menit_rencana=30)).status_code == 201

    r = c.get(f"{URL}/rekap-orang", params={"limit": 100})
    assert r.status_code == 200, r.text
    rekap = {x["kode_orang"]: x for x in r.json()["items"] if x["kode_orang"] in {a, b}}
    assert len(rekap) == 2
    assert rekap[a] == {
        "kode_orang": a,
        "jumlah_sesi": 2,
        "total_menit_rencana": 90,
        "total_menit_disepakati": 45,
    }
    assert rekap[b]["jumlah_sesi"] == 1
    assert rekap[b]["total_menit_rencana"] == 60
    assert rekap[b]["total_menit_disepakati"] is None


def test_rekap_null_diabaikan_bukan_nol(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "ss-2")
    a = _kode(c)
    c.post(URL, json=_sesi("S-11", a, menit_disepakati=30))
    c.post(URL, json=_sesi("S-12", a))
    rk = _rekap(c, a)
    assert rk["jumlah_sesi"] == 2
    assert rk["total_menit_disepakati"] == 30
    assert rk["total_menit_rencana"] is None


def test_create_dua_masalah_get_search_dan_riwayat(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "ss-3")
    a = _kode(c)
    m1, m2 = _masalah_id(db_session, "M-K01-01"), _masalah_id(db_session, "M-K02-01")
    r = c.post(URL, json=_sesi("S-21", a, masalah_ids=[m1, m2]))
    assert r.status_code == 201, r.text
    s = r.json()
    assert s["status_izin"] == "Belum ditetapkan"
    got = c.get(f"{URL}/{s['id']}")
    assert got.status_code == 200, got.text
    assert sorted(got.json()["masalah_ids"]) == sorted([m1, m2])

    cari = c.post(
        f"{URL}/search",
        json={"domain": [["jenis_kegiatan", "=", "Klarifikasi"], ["kode_orang", "=", a]]},
    )
    assert cari.status_code == 200, cari.text
    assert [x["id"] for x in cari.json()["items"]] == [s["id"]]
    assert c.get(URL).json()["total"] >= 1

    rw = RedesainRiwayatModel
    aksi = db_session.scalars(
        select(rw.aksi).where(rw.entitas == "sesi", rw.entitas_id == s["id"])
    ).all()
    assert list(aksi) == ["create"]


def test_status_tidak_diotorisasi_tetap_tersimpan(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "ss-4")
    a = _kode(c)
    r = c.post(URL, json=_sesi("S-31", a, status_izin="Tidak diotorisasi"))
    assert r.status_code == 201, r.text
    assert r.json()["status_izin"] == "Tidak diotorisasi"
    p = c.patch(f"{URL}/{r.json()['id']}", json={"menit_disepakati": 20})
    assert p.status_code == 200, p.text


def test_patch_ganti_penuh_masalah_dan_pasangan_ganda_409(
    client_as, partisipan_factory, db_session
):
    c = _tim(client_as, partisipan_factory, "ss-5")
    a, b = _kode(c), _kode(c)
    m1, m2 = _masalah_id(db_session, "M-K01-01"), _masalah_id(db_session, "M-K02-01")
    s1 = c.post(URL, json=_sesi("S-41", a, masalah_ids=[m1])).json()
    s2 = c.post(URL, json=_sesi("S-41", b)).json()

    p = c.patch(f"{URL}/{s1['id']}", json={"masalah_ids": [m2]})
    assert p.status_code == 200, p.text
    assert p.json()["masalah_ids"] == [m2]

    ganda = c.post(URL, json=_sesi("S-41", a))
    assert ganda.status_code == 409, ganda.text
    ganda_patch = c.patch(f"{URL}/{s2['id']}", json={"kode_orang": a})
    assert ganda_patch.status_code == 409, ganda_patch.text


def test_validasi_menit_negatif_kode_orang_dan_masalah_422(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "ss-6")
    a = _kode(c)
    assert c.post(URL, json=_sesi("S-51", a, menit_rencana=-5)).status_code == 422
    assert c.post(URL, json=_sesi("S-51", "O-9999")).status_code == 422
    assert c.post(URL, json=_sesi("S-51", a, masalah_ids=["tidak-ada"])).status_code == 422
    assert c.post(URL, json=_sesi("S-51", a, pic_kode_orang="O-9999")).status_code == 422
    s = c.post(URL, json=_sesi("S-51", a)).json()
    assert c.patch(f"{URL}/{s['id']}", json={"menit_disepakati": -1}).status_code == 422
    assert c.get(f"{URL}/tidak-ada").status_code == 404


def test_sekolah_pengisi_ditolak_403(client_as, partisipan_factory):
    partisipan_factory("ss-7")
    sp = client_as("ss-7", groups=["sekolah-pengisi"])
    assert sp.get(f"{URL}/rekap-orang").status_code == 403
    assert sp.get(URL).status_code == 403
    assert sp.post(URL, json=_sesi("S-61", "O-0001")).status_code == 403
