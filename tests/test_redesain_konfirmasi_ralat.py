"""Tes ralat, daftar Tim, angkat masalah baru, dan isian luring konfirmasi (backlog `#55`)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from anjab_abk_backend.models import (
    RedesainKonteksModel,
    RedesainMasalahModel,
    RedesainRiwayatModel,
)

URL = "/api/v1/redesain/konfirmasi"
MASALAH = "/api/v1/redesain/masalah"

PENILAIAN = {
    "kesesuaian": "Sebagian",
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
        json={"nama": f"SD Ral {label} {npsn}", "npsn": npsn, "jenjang_pendidikan_id": "jp_x"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _tim(client_as, partisipan_factory):
    subject = f"tim-{uuid.uuid4().hex[:6]}"
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _konteks_id(db_session, kode: str = "K-01") -> str:
    return db_session.scalars(
        select(RedesainKonteksModel.id).where(RedesainKonteksModel.kode == kode)
    ).one()


def _masalah(client_as, partisipan_factory, db_session, sekolah_id: str) -> str:
    tim = _tim(client_as, partisipan_factory)
    r = tim.post(
        MASALAH,
        json={
            "konteks_id": _konteks_id(db_session),
            "sekolah_id": sekolah_id,
            "periode_acuan": "TA 2026/27",
            "rumusan_hipotesis": "Jadwal disusun manual.",
            "sumber_awal_keterbatasan": "Catatan rapat.",
            "gelombang": "G1",
        },
    )
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    b = tim.post(f"{MASALAH}/{mid}/status-konfirmasi", json={"dibuka": True})
    assert b.status_code == 200, b.text
    return mid


def _pengisi(client_as, partisipan_factory, sekolah_id: str):
    subject = f"skl-{uuid.uuid4().hex[:6]}"
    partisipan_factory(subject, sekolah_id=sekolah_id)
    return client_as(subject, groups=["sekolah-pengisi"])


def _kirim(c, mid: str, **tambahan) -> str:
    """Isi satu konfirmasi sampai terkirim; kembalikan id-nya."""
    kid = c.post(URL, json={"masalah_id": mid}).json()["id"]
    c.patch(f"{URL}/{kid}", json={"cerita_sebelum": "Cerita kami."})
    assert c.post(f"{URL}/{kid}/kunci-cerita").status_code == 200
    assert c.post(f"{URL}/{kid}/tampilkan-dugaan").status_code == 200
    p = c.patch(f"{URL}/{kid}", json={"peran": "Guru", **PENILAIAN, **tambahan})
    assert p.status_code == 200, p.text
    k = c.post(f"{URL}/{kid}/kirim")
    assert k.status_code == 200, k.text
    return kid


def test_ralat_membuat_versi_baru_dan_daftar_saya(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "a")
    mid = _masalah(client_as, partisipan_factory, db_session, skl)
    c = _pengisi(client_as, partisipan_factory, skl)
    lama = _kirim(c, mid)

    r = c.post(f"{URL}/{lama}/ralat")
    assert r.status_code == 201, r.text
    baru = r.json()
    assert baru["menggantikan_id"] == lama
    assert baru["status"] == "draf"
    assert baru["cerita_sebelum"] == "Cerita kami."
    assert baru["cerita_dikunci_pada"] is not None
    assert baru["dugaan_diperlihatkan"] == "Ya"
    assert baru["k1"] == "Tinggi"

    # versi lama tak berubah
    asli = c.get(f"{URL}/{lama}").json()
    assert asli["status"] == "terkirim"
    assert asli["menggantikan_id"] is None

    # ralat langsung bisa diedit (cerita tak dibuka ulang) dan dikirim
    assert c.patch(f"{URL}/{baru['id']}", json={"k1": "Rendah"}).status_code == 200
    assert c.post(f"{URL}/{baru['id']}/kirim").status_code == 200

    saya = c.get(f"{URL}/saya").json()
    assert saya["total"] == 2
    by_id = {x["id"]: x for x in saya["items"]}
    assert by_id[lama]["digantikan"] is True
    assert by_id[baru["id"]]["digantikan"] is False

    aksi = [
        x.aksi
        for x in db_session.scalars(
            select(RedesainRiwayatModel).where(
                RedesainRiwayatModel.entitas == "konfirmasi",
                RedesainRiwayatModel.entitas_id == baru["id"],
            )
        ).all()
    ]
    assert "ralat" in aksi

    tim = _tim(client_as, partisipan_factory)
    s = tim.post(f"{URL}/search", json={"domain": [["status", "=", "terkirim"]]})
    assert s.status_code == 200, s.text
    ids = {x["id"] for x in s.json()["items"]}
    assert {lama, baru["id"]} <= ids


def test_ralat_draf_dan_yang_sudah_digantikan_409(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "b")
    mid = _masalah(client_as, partisipan_factory, db_session, skl)
    c = _pengisi(client_as, partisipan_factory, skl)
    draf = c.post(URL, json={"masalah_id": mid}).json()["id"]
    r = c.post(f"{URL}/{draf}/ralat")
    assert r.status_code == 409
    assert r.json()["error"] == "KONFIRMASI_BELUM_TERKIRIM"

    # lengkapi draf itu, lalu ralat dua kali
    c.patch(f"{URL}/{draf}", json={"cerita_sebelum": "Cerita."})
    c.post(f"{URL}/{draf}/kunci-cerita")
    c.post(f"{URL}/{draf}/tampilkan-dugaan")
    c.patch(f"{URL}/{draf}", json={"peran": "Guru", **PENILAIAN})
    assert c.post(f"{URL}/{draf}/kirim").status_code == 200
    assert c.post(f"{URL}/{draf}/ralat").status_code == 201
    kedua = c.post(f"{URL}/{draf}/ralat")
    assert kedua.status_code == 409
    assert kedua.json()["error"] == "KONFIRMASI_SUDAH_DIGANTIKAN"


def test_ralat_milik_orang_lain_403(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "c")
    mid = _masalah(client_as, partisipan_factory, db_session, skl)
    a = _pengisi(client_as, partisipan_factory, skl)
    kid = _kirim(a, mid)
    b = _pengisi(client_as, partisipan_factory, skl)
    assert b.post(f"{URL}/{kid}/ralat").status_code == 403


def test_daftar_tim_hanya_tim_kajian(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "d")
    mid = _masalah(client_as, partisipan_factory, db_session, skl)
    c = _pengisi(client_as, partisipan_factory, skl)
    kid = _kirim(c, mid)

    assert c.get(URL).status_code == 403
    assert c.post(f"{URL}/search", json={"domain": []}).status_code == 403

    tim = _tim(client_as, partisipan_factory)
    daftar = tim.get(URL)
    assert daftar.status_code == 200, daftar.text
    assert kid in {x["id"] for x in daftar.json()["items"]}
    cari = tim.post(f"{URL}/search", json={"domain": [["masalah_id", "=", mid]]})
    assert [x["id"] for x in cari.json()["items"]] == [kid]
    asing = tim.post(f"{URL}/search", json={"domain": [["cerita_sebelum", "=", "x"]]})
    assert asing.status_code == 422


def test_angkat_masalah_membuat_keterangan_kasus(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "e")
    mid = _masalah(client_as, partisipan_factory, db_session, skl)
    c = _pengisi(client_as, partisipan_factory, skl)
    kid = _kirim(c, mid, masalah_baru="Presensi siswa ditulis dua kali.")
    tim = _tim(client_as, partisipan_factory)
    konteks = _konteks_id(db_session, "K-02")

    r = tim.post(
        f"{URL}/{kid}/angkat-masalah",
        json={"konteks_id": konteks, "rumusan_hipotesis": "Presensi dicatat ganda."},
    )
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["status_awal"] == "Keterangan kasus"
    assert m["sumber_konfirmasi_id"] == kid
    assert m["sekolah_id"] == skl
    assert m["gelombang"] == "Belum dijadwalkan"
    assert m["sumber_awal_keterbatasan"] == f"Disebut dalam konfirmasi {kid}"
    assert m["kode"].startswith("M-K02-")
    assert m["status_awal_dibekukan_pada"] is None
    # teks asli di konfirmasi tak berubah
    assert tim.get(f"{URL}/{kid}").json()["masalah_baru"] == "Presensi siswa ditulis dua kali."

    ulang = tim.post(
        f"{URL}/{kid}/angkat-masalah",
        json={"konteks_id": konteks, "rumusan_hipotesis": "Lagi."},
    )
    assert ulang.status_code == 409
    assert ulang.json()["error"] == "MASALAH_SUDAH_DIANGKAT"


def test_angkat_masalah_tanpa_masalah_baru_422(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "f")
    mid = _masalah(client_as, partisipan_factory, db_session, skl)
    c = _pengisi(client_as, partisipan_factory, skl)
    kid = _kirim(c, mid)
    body = {"konteks_id": _konteks_id(db_session), "rumusan_hipotesis": "X"}
    # client_as menimpa identitas: pengisi dibuat ulang setelah tim
    tim = _tim(client_as, partisipan_factory)
    assert tim.post(f"{URL}/{kid}/angkat-masalah", json=body).status_code == 422
    c2 = _pengisi(client_as, partisipan_factory, skl)
    assert c2.post(f"{URL}/{kid}/angkat-masalah", json=body).status_code == 403


def _luring_body(mid: str, skl: str, kode: str, **tambahan) -> dict:
    return {
        "masalah_id": mid,
        "kode_orang": kode,
        "sekolah_id": skl,
        "peran": "Kepala sekolah",
        "cerita_sebelum": "Dari lembar kertas.",
        **PENILAIAN,
        **tambahan,
    }


def test_luring_terkirim_membekukan_dan_eskalasi(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "g")
    mid = _masalah(client_as, partisipan_factory, db_session, skl)
    pemberi = _pengisi(client_as, partisipan_factory, skl)
    kode = pemberi.get("/api/v1/redesain/kode-orang/saya").json()["kode"]
    tim = _tim(client_as, partisipan_factory)

    r = tim.post(URL + "/luring", json=_luring_body(mid, skl, kode, indikasi_risiko="Ada indikasi"))
    assert r.status_code == 201, r.text
    k = r.json()
    assert k["sumber"] == "luring"
    assert k["status"] == "terkirim"
    assert k["kode_orang"] == kode
    assert k["cerita_dikunci_pada"] is None
    assert k["dugaan_ditampilkan_pada"] is None
    assert k["dugaan_diperlihatkan"] == "Belum"
    assert k["dikirim_pada"] is not None

    db_session.expire_all()
    masalah = db_session.get(RedesainMasalahModel, mid)
    assert masalah.status_awal_dibekukan_pada is not None
    assert masalah.eskalasi_pada is not None

    cari = tim.post(f"{MASALAH}/search", json={"domain": [["eskalasi_pada", "!=", None]]})
    assert mid in {x["id"] for x in cari.json()["items"]}
    assert tim.get(f"{MASALAH}/{mid}").json()["eskalasi_pada"] is not None

    ganda = tim.post(URL + "/luring", json=_luring_body(mid, skl, kode))
    assert ganda.status_code == 409


def test_luring_validasi_dan_otorisasi(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "h")
    sekolah_lain = _sekolah(client_as, "h2")
    mid = _masalah(client_as, partisipan_factory, db_session, skl)
    pemberi = _pengisi(client_as, partisipan_factory, skl)
    kode = pemberi.get("/api/v1/redesain/kode-orang/saya").json()["kode"]
    kurang = _luring_body(mid, skl, kode)
    del kurang["k3"]

    # client_as menimpa identitas: pakai tim yang baru dibuat untuk tiap panggilan
    tim = _tim(client_as, partisipan_factory)
    assert tim.post(URL + "/luring", json=_luring_body(mid, skl, "O-9999")).status_code == 422
    assert tim.post(URL + "/luring", json=kurang).status_code == 422
    salah = _luring_body(mid, sekolah_lain, kode)
    assert tim.post(URL + "/luring", json=salah).status_code == 422
    pemberi2 = _pengisi(client_as, partisipan_factory, skl)
    assert pemberi2.post(URL + "/luring", json=_luring_body(mid, skl, kode)).status_code == 403
