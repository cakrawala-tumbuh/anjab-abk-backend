"""Tes penilaian redesain: CRUD+search Tim, saran triase tersimpan, 409/422/403 (backlog `#57`)."""

from __future__ import annotations

from sqlalchemy import select

from anjab_abk_backend.models import RedesainMasalahModel, RedesainRiwayatModel

URL = "/api/v1/redesain/penilaian"


def _masalah_id(db_session, kode: str = "M-K01-01") -> str:
    return db_session.scalars(
        select(RedesainMasalahModel.id).where(RedesainMasalahModel.kode == kode)
    ).one()


def _tim(client_as, partisipan_factory, subject: str):
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _t03(masalah_id: str, **kw):
    base = {
        "masalah_id": masalah_id,
        "status_bukti": "Diperkuat untuk klaim",
        "gap_material": "Tidak",
        "indikasi_kritis": "Tidak terlihat",
        "k1": "Sedang",
        "k2": "Rendah",
        "k3": "Tinggi",
        "k4": "Tinggi",
    }
    base.update(kw)
    return base


def test_create_t03_lalu_patch_k3_rendah_hitung_ulang_dan_riwayat(
    client_as, partisipan_factory, db_session
):
    c = _tim(client_as, partisipan_factory, "pnl-1")
    mid = _masalah_id(db_session)
    r = c.post(URL, json=_t03(mid))
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["saran_otomatis"] == "P1 - Utama"
    assert p["versi_aturan_triase"] == "v1.3"

    u = c.patch(f"{URL}/{p['id']}", json={"k3": "Rendah"})
    assert u.status_code == 200, u.text
    assert u.json()["saran_otomatis"] == "P2 - Berikutnya"
    assert u.json()["k4"] == "Tinggi"

    assert c.get(f"{URL}/{p['id']}").json()["saran_otomatis"] == "P2 - Berikutnya"
    assert c.get(URL).json()["total"] >= 1
    s = c.post(f"{URL}/search", json={"domain": [["saran_otomatis", "=", "P2 - Berikutnya"]]})
    assert s.status_code == 200, s.text
    assert [x["id"] for x in s.json()["items"]] == [p["id"]]

    rw = RedesainRiwayatModel
    rows = db_session.scalars(
        select(rw).where(rw.entitas == "penilaian", rw.entitas_id == p["id"])
    ).all()
    assert sorted(x.aksi for x in rows) == ["create", "update"]
    upd = next(x for x in rows if x.aksi == "update")
    assert upd.nilai_sesudah["saran_otomatis"] == "P2 - Berikutnya"


def test_saran_di_payload_diabaikan(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-2")
    mid = _masalah_id(db_session)
    r = c.post(
        URL,
        json=_t03(mid, saran_otomatis="P3 - Pantau", versi_aturan_triase="v0"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["saran_otomatis"] == "P1 - Utama"
    assert r.json()["versi_aturan_triase"] == "v1.3"
    u = c.patch(f"{URL}/{r.json()['id']}", json={"saran_otomatis": "P0 - Eskalasi"})
    assert u.status_code == 200, u.text
    assert u.json()["saran_otomatis"] == "P1 - Utama"


def test_belum_cukup_klarifikasi_dan_k_kosong(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-3")
    r = c.post(URL, json=_t03(_masalah_id(db_session), status_bukti="Belum cukup"))
    assert r.status_code == 201, r.text
    assert r.json()["saran_otomatis"] == "K - Klarifikasi"
    kosong = c.post(
        URL,
        json={
            "masalah_id": _masalah_id(db_session, "M-K02-01"),
            "status_bukti": "Diperkuat untuk klaim",
            "gap_material": "Tidak",
            "indikasi_kritis": "Tidak terlihat",
        },
    )
    assert kosong.status_code == 201, kosong.text
    assert kosong.json()["k1"] is None
    assert kosong.json()["saran_otomatis"] == "K - Klarifikasi"


def test_create_kedua_409_dan_validasi_422(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "pnl-4")
    mid = _masalah_id(db_session)
    assert c.post(URL, json=_t03(mid)).status_code == 201
    assert c.post(URL, json=_t03(mid)).status_code == 409
    assert c.post(URL, json=_t03(mid, indikasi_kritis="Ya")).status_code == 422
    assert c.post(URL, json=_t03("tidak-ada")).status_code == 422
    assert c.post(URL, json=_t03(mid, asing="x")).status_code == 422
    assert c.get(f"{URL}/tidak-ada").status_code == 404


def test_sekolah_pengisi_ditolak_403(client_as, partisipan_factory, db_session):
    partisipan_factory("pnl-5")
    sp = client_as("pnl-5", groups=["sekolah-pengisi"])
    assert sp.get(URL).status_code == 403
    assert sp.post(URL, json=_t03(_masalah_id(db_session))).status_code == 403
    assert sp.post(f"{URL}/search", json={"domain": []}).status_code == 403
