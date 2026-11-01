"""Tes konfirmasi sekolah redesain: urutan cerita-sebelum-dugaan & eskalasi (backlog `#53`)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from anjab_abk_backend.models import (
    RedesainKonteksModel,
    RedesainMasalahModel,
    RedesainRiwayatModel,
)

URL = "/api/v1/redesain/konfirmasi"
URL_SEKOLAH = "/api/v1/redesain/sekolah/masalah"
HIPOTESIS = "Jadwal pelajaran disusun manual berulang setiap semester."

PENILAIAN = {
    "kesesuaian": "Sebagian",
    "koreksi": "Hanya untuk kelas atas.",
    "k1": "Tinggi",
    "k2": "Sedang",
    "k3": "Rendah",
    "k4": "Belum tahu",
    "indikasi_risiko": "Tidak terlihat",
}


def _sekolah(client_as, label: str) -> str:
    admin = client_as(f"admin-{label}", groups=["admin"])
    npsn = str(uuid.uuid4().int)[:8]
    r = admin.post(
        "/api/v1/sekolah",
        json={"nama": f"SD Konf {label} {npsn}", "npsn": npsn, "jenjang_pendidikan_id": "jp_x"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _masalah(client_as, partisipan_factory, db_session, sekolah_id: str, *, dibuka=True) -> str:
    """Buat masalah lewat API Tim untuk `sekolah_id`, lalu buka untuk konfirmasi."""
    subject = f"tim-{uuid.uuid4().hex[:6]}"
    partisipan_factory(subject)
    tim = client_as(subject, groups=["tim-kajian"])
    konteks_id = db_session.scalars(
        select(RedesainKonteksModel.id).where(RedesainKonteksModel.kode == "K-01")
    ).one()
    r = tim.post(
        "/api/v1/redesain/masalah",
        json={
            "konteks_id": konteks_id,
            "sekolah_id": sekolah_id,
            "periode_acuan": "TA 2026/27",
            "rumusan_hipotesis": HIPOTESIS,
            "sumber_awal_keterbatasan": "Catatan rapat; belum diverifikasi.",
            "gelombang": "G1",
        },
    )
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    if dibuka:
        b = tim.post(f"/api/v1/redesain/masalah/{mid}/status-konfirmasi", json={"dibuka": True})
        assert b.status_code == 200, b.text
    return mid


def _pengisi(client_as, partisipan_factory, sekolah_id: str, subject: str | None = None):
    subject = subject or f"skl-{uuid.uuid4().hex[:6]}"
    partisipan_factory(subject, sekolah_id=sekolah_id)
    return client_as(subject, groups=["sekolah-pengisi"])


def _masalah_db(db_session, mid: str) -> RedesainMasalahModel:
    db_session.expire_all()
    return db_session.get(RedesainMasalahModel, mid)


def test_alur_penuh_sampai_kirim_dan_riwayat(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "a")
    mid = _masalah(client_as, partisipan_factory, db_session, skl)
    c = _pengisi(client_as, partisipan_factory, skl)

    daftar = c.get(URL_SEKOLAH)
    assert daftar.status_code == 200, daftar.text
    item = next(x for x in daftar.json()["items"] if x["id"] == mid)
    assert "rumusan_hipotesis" not in item
    assert item["konteks_kode"] == "K-01"
    assert HIPOTESIS not in daftar.text

    r = c.post(URL, json={"masalah_id": mid})
    assert r.status_code == 201, r.text
    kid = r.json()["id"]
    assert r.json()["status"] == "draf"
    assert r.json()["sumber"] == "daring"
    assert r.json()["sekolah_id"] == skl
    assert r.json()["dugaan_diperlihatkan"] == "Belum"

    p = c.patch(f"{URL}/{kid}", json={"cerita_sebelum": "Kami menyusun jadwal tiap semester."})
    assert p.status_code == 200, p.text

    belum = c.post(f"{URL}/{kid}/tampilkan-dugaan")
    assert belum.status_code == 409
    assert belum.json()["error"] == "CERITA_BELUM_DIKUNCI"

    k = c.post(f"{URL}/{kid}/kunci-cerita")
    assert k.status_code == 200, k.text
    assert k.json()["cerita_dikunci_pada"] is not None

    d = c.post(f"{URL}/{kid}/tampilkan-dugaan")
    assert d.status_code == 200, d.text
    assert d.json()["rumusan_hipotesis"] == HIPOTESIS
    assert d.json()["dugaan_ditampilkan_pada"]
    assert c.get(f"{URL}/{kid}").json()["dugaan_diperlihatkan"] == "Ya"

    p2 = c.patch(f"{URL}/{kid}", json={"peran": "Guru kelas", **PENILAIAN})
    assert p2.status_code == 200, p2.text

    kirim = c.post(f"{URL}/{kid}/kirim")
    assert kirim.status_code == 200, kirim.text
    assert kirim.json()["status"] == "terkirim"
    assert kirim.json()["dikirim_pada"] is not None

    masalah = _masalah_db(db_session, mid)
    assert masalah.status_awal_dibekukan_pada is not None
    assert masalah.eskalasi_pada is None

    rw = RedesainRiwayatModel
    aksi = [
        x.aksi
        for x in db_session.scalars(
            select(rw).where(rw.entitas == "konfirmasi", rw.entitas_id == kid)
        ).all()
    ]
    assert "kirim" in aksi
    assert {"create", "kunci_cerita", "tampilkan_dugaan"} <= set(aksi)

    sesudah = c.patch(f"{URL}/{kid}", json={"peran": "Kepala sekolah"})
    assert sesudah.status_code == 409
    assert c.post(f"{URL}/{kid}/kirim").status_code == 409


def test_gerbang_urutan_patch_dan_kunci_kosong(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "b")
    mid = _masalah(client_as, partisipan_factory, db_session, skl)
    c = _pengisi(client_as, partisipan_factory, skl)
    kid = c.post(URL, json={"masalah_id": mid}).json()["id"]

    kosong = c.post(f"{URL}/{kid}/kunci-cerita")
    assert kosong.status_code == 422
    c.patch(f"{URL}/{kid}", json={"cerita_sebelum": "   "})
    assert c.post(f"{URL}/{kid}/kunci-cerita").status_code == 422

    dini = c.patch(f"{URL}/{kid}", json={"k1": "Tinggi"})
    assert dini.status_code == 409
    assert dini.json()["error"] == "DUGAAN_BELUM_DITAMPILKAN"

    c.patch(f"{URL}/{kid}", json={"cerita_sebelum": "Cerita kami."})
    assert c.post(f"{URL}/{kid}/kunci-cerita").status_code == 200
    ubah = c.patch(f"{URL}/{kid}", json={"cerita_sebelum": "Cerita lain."})
    assert ubah.status_code == 409
    assert ubah.json()["error"] == "CERITA_SUDAH_DIKUNCI"


def test_kirim_field_kosong_dan_create_ganda(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "c")
    mid = _masalah(client_as, partisipan_factory, db_session, skl)
    c = _pengisi(client_as, partisipan_factory, skl)
    kid = c.post(URL, json={"masalah_id": mid}).json()["id"]

    ganda = c.post(URL, json={"masalah_id": mid})
    assert ganda.status_code == 409

    c.patch(f"{URL}/{kid}", json={"cerita_sebelum": "Cerita."})
    c.post(f"{URL}/{kid}/kunci-cerita")
    c.post(f"{URL}/{kid}/tampilkan-dugaan")
    tanpa_k3 = {k: v for k, v in PENILAIAN.items() if k != "k3"}
    assert c.patch(f"{URL}/{kid}", json={"peran": "Guru", **tanpa_k3}).status_code == 200

    r = c.post(f"{URL}/{kid}/kirim")
    assert r.status_code == 422
    assert "k3" in r.json()["message"]
    assert [d["loc"][-1] for d in r.json()["details"]] == ["k3"]


def test_kirim_ada_indikasi_mengisi_eskalasi(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "d")
    mid = _masalah(client_as, partisipan_factory, db_session, skl)
    c = _pengisi(client_as, partisipan_factory, skl)
    kid = c.post(URL, json={"masalah_id": mid}).json()["id"]
    c.patch(f"{URL}/{kid}", json={"cerita_sebelum": "Cerita."})
    c.post(f"{URL}/{kid}/kunci-cerita")
    c.post(f"{URL}/{kid}/tampilkan-dugaan")
    c.patch(f"{URL}/{kid}", json={"peran": "Guru", **PENILAIAN, "indikasi_risiko": "Ada indikasi"})
    assert c.post(f"{URL}/{kid}/kirim").status_code == 200

    masalah = _masalah_db(db_session, mid)
    assert masalah.eskalasi_pada is not None
    assert masalah.status_awal_dibekukan_pada is not None


def test_lingkup_sekolah_dan_masalah_belum_dibuka(client_as, partisipan_factory, db_session):
    skl_a = _sekolah(client_as, "e1")
    skl_b = _sekolah(client_as, "e2")
    mid_a = _masalah(client_as, partisipan_factory, db_session, skl_a)
    mid_tutup = _masalah(client_as, partisipan_factory, db_session, skl_a, dibuka=False)

    a = _pengisi(client_as, partisipan_factory, skl_a, "skl-a-1")
    kid = a.post(URL, json={"masalah_id": mid_a}).json()["id"]
    assert a.post(URL, json={"masalah_id": mid_tutup}).status_code == 403
    assert all(x["id"] != mid_tutup for x in a.get(URL_SEKOLAH).json()["items"])

    b = _pengisi(client_as, partisipan_factory, skl_b, "skl-b-1")
    assert b.post(URL, json={"masalah_id": mid_a}).status_code == 403
    assert b.get(f"{URL}/{kid}").status_code == 403
    assert b.patch(f"{URL}/{kid}", json={"peran": "x"}).status_code == 403
    assert b.post(f"{URL}/{kid}/kunci-cerita").status_code == 403
    assert all(x["id"] != mid_a for x in b.get(URL_SEKOLAH).json()["items"])

    partisipan_factory("tim-baca")
    tim = client_as("tim-baca", groups=["tim-kajian"])
    assert tim.get(f"{URL}/{kid}").status_code == 200
    assert tim.post(URL, json={"masalah_id": mid_a}).status_code == 403


def test_tanpa_token_dan_tidak_ditemukan(anon_client, client_as, partisipan_factory):
    assert anon_client.get(URL_SEKOLAH).status_code == 401
    assert anon_client.post(URL, json={"masalah_id": "x"}).status_code == 401
    skl = _sekolah(client_as, "f")
    c = _pengisi(client_as, partisipan_factory, skl)
    assert c.post(URL, json={"masalah_id": "tidak-ada"}).status_code == 404
    assert c.get(f"{URL}/tidak-ada").status_code == 404
