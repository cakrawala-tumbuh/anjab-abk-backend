"""Tes ALUR redesain: proses & langkah per masalah × sekolah (backlog `#52`)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from anjab_abk_backend.models import RedesainMasalahModel, RedesainRiwayatModel

URL = "/api/v1/redesain/proses"
URL_LANGKAH = "/api/v1/redesain/langkah"


def _masalah_id(db_session, kode: str = "M-K01-01") -> str:
    return db_session.scalars(
        select(RedesainMasalahModel.id).where(RedesainMasalahModel.kode == kode)
    ).one()


def _sekolah(client_as, label: str) -> str:
    admin = client_as(f"admin-{label}", groups=["admin"])
    npsn = str(uuid.uuid4().int)[:8]
    r = admin.post(
        "/api/v1/sekolah",
        json={"nama": f"SD Alur {label} {npsn}", "npsn": npsn, "jenjang_pendidikan_id": "jp_dummy"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _tim(client_as, partisipan_factory, subject: str):
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _proses(masalah_id: str, sekolah_id: str, **kw):
    base = {
        "masalah_id": masalah_id,
        "sekolah_id": sekolah_id,
        "periode": "TA 2026/27",
        "nama_proses": "Penyusunan jadwal pelajaran",
    }
    base.update(kw)
    return base


def _langkah(**kw):
    base = {
        "tahap": "Pengumpulan data",
        "pemicu_input": "Awal semester",
        "pelaksana": "Wakil Kepala Sekolah Kurikulum",
        "pekerjaan_sistem": "Spreadsheet jadwal",
        "keluaran_penerima": "Draf jadwal ke kepala sekolah",
        "status_langkah": "Hipotesis",
    }
    base.update(kw)
    return base


def _riwayat_alur(db_session, ids: set[str]) -> list[RedesainRiwayatModel]:
    rw = RedesainRiwayatModel
    return list(
        db_session.scalars(
            select(rw).where(rw.entitas.in_(["proses", "langkah"]), rw.entitas_id.in_(ids))
        ).all()
    )


def test_create_proses_dua_langkah_kode_urutan_dan_riwayat(
    client_as, partisipan_factory, db_session
):
    skl = _sekolah(client_as, "a")
    c = _tim(client_as, partisipan_factory, "tka-1")
    r = c.post(URL, json=_proses(_masalah_id(db_session), skl))
    assert r.status_code == 201, r.text
    proses = r.json()
    assert proses["kode"] == "P-001"
    assert proses["langkah"] == []

    l1 = c.post(f"{URL}/{proses['id']}/langkah", json=_langkah(urutan=2, tahap="Kedua"))
    assert l1.status_code == 201, l1.text
    l2 = c.post(f"{URL}/{proses['id']}/langkah", json=_langkah(urutan=1, tahap="Pertama"))
    assert l2.status_code == 201, l2.text
    assert l1.json()["kode"] == "P-001-S01"
    assert l2.json()["kode"] == "P-001-S02"
    l3 = c.post(f"{URL}/{proses['id']}/langkah", json=_langkah(tahap="Ketiga"))
    assert l3.json()["urutan"] == 3

    got = c.get(f"{URL}/{proses['id']}")
    assert got.status_code == 200
    assert [x["tahap"] for x in got.json()["langkah"]] == ["Pertama", "Kedua", "Ketiga"]

    ids = {proses["id"], l1.json()["id"], l2.json()["id"]}
    rows = _riwayat_alur(db_session, ids)
    assert len(rows) == 3
    assert sorted(r.entitas for r in rows) == ["langkah", "langkah", "proses"]
    assert all(r.aksi == "create" and r.pelaku_kode_orang for r in rows)

    kedua = c.post(URL, json=_proses(_masalah_id(db_session, "M-K02-01"), skl))
    assert kedua.json()["kode"] == "P-002"


def test_status_langkah_kosakata_dan_patch(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "b")
    c = _tim(client_as, partisipan_factory, "tka-2")
    proses = c.post(URL, json=_proses(_masalah_id(db_session), skl)).json()
    salah = c.post(
        f"{URL}/{proses['id']}/langkah",
        json=_langkah(status_langkah="Diperkuat sesuai klaim"),
    )
    assert salah.status_code == 422
    benar = c.post(
        f"{URL}/{proses['id']}/langkah",
        json=_langkah(status_langkah="Diperkuat untuk klaim", hambatan="Data terlambat"),
    )
    assert benar.status_code == 201, benar.text
    lid = benar.json()["id"]

    p = c.patch(f"{URL_LANGKAH}/{lid}", json={"status_langkah": "Tidak berlaku", "hambatan": None})
    assert p.status_code == 200, p.text
    assert p.json()["status_langkah"] == "Tidak berlaku"
    assert p.json()["hambatan"] is None
    assert p.json()["kode"] == "P-001-S01"
    assert (
        c.patch(f"{URL_LANGKAH}/{lid}", json={"status_langkah": "Belum cukup"}).status_code == 422
    )
    aksi = [r.aksi for r in _riwayat_alur(db_session, {lid})]
    assert sorted(aksi) == ["create", "update"]

    assert c.patch(f"{URL_LANGKAH}/tidak-ada", json={"tahap": "x"}).status_code == 404
    assert c.post(f"{URL}/tidak-ada/langkah", json=_langkah()).status_code == 404


def test_search_masalah_id(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "c")
    c = _tim(client_as, partisipan_factory, "tka-3")
    m1 = _masalah_id(db_session, "M-K01-01")
    p1 = c.post(URL, json=_proses(m1, skl)).json()
    c.post(URL, json=_proses(_masalah_id(db_session, "M-K02-01"), skl))
    r = c.post(f"{URL}/search", json={"domain": [["masalah_id", "=", m1]]})
    assert r.status_code == 200, r.text
    assert [i["id"] for i in r.json()["items"]] == [p1["id"]]
    assert c.get(URL).json()["total"] == 2
    assert c.post(f"{URL}/search", json={"domain": [["periode", "=", "x"]]}).status_code == 422


def test_sekolah_proses_wajib_sama_dengan_masalah_bersekolah(
    client_as, partisipan_factory, db_session
):
    skl_a = _sekolah(client_as, "d1")
    skl_b = _sekolah(client_as, "d2")
    mid = _masalah_id(db_session, "M-K03-01")
    rec = db_session.get(RedesainMasalahModel, mid)
    rec.sekolah_id = skl_a
    db_session.flush()
    c = _tim(client_as, partisipan_factory, "tka-4")
    beda = c.post(URL, json=_proses(mid, skl_b))
    assert beda.status_code == 422
    assert "berbeda" in beda.text
    sama = c.post(URL, json=_proses(mid, skl_a))
    assert sama.status_code == 201, sama.text
    assert c.patch(f"{URL}/{sama.json()['id']}", json={"sekolah_id": skl_b}).status_code == 422
    ok = c.patch(f"{URL}/{sama.json()['id']}", json={"nama_proses": "Rapat kurikulum"})
    assert ok.status_code == 200
    assert ok.json()["nama_proses"] == "Rapat kurikulum"
    assert ok.json()["kode"] == "P-001"


def test_negatif_rujukan_dan_akses(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "e")
    c = _tim(client_as, partisipan_factory, "tka-5")
    assert c.post(URL, json=_proses("tidak-ada", skl)).status_code == 422
    assert c.post(URL, json=_proses(_masalah_id(db_session), "skl_x")).status_code == 422
    assert c.post(URL, json=_proses(_masalah_id(db_session), skl, kode="P-9")).status_code == 422
    assert c.get(f"{URL}/zzz").status_code == 404
    assert c.patch(f"{URL}/zzz", json={"periode": "x"}).status_code == 404
    assert c.delete(f"{URL}/zzz").status_code == 405
    partisipan_factory("spa-1")
    assert client_as("spa-1", groups=["sekolah-pengisi"]).get(URL).status_code == 403
    assert client_as("spa-1", groups=["admin"]).get(URL).status_code == 403
