"""Tes bukti redesain: CRUD+search Tim, kode `B-NNNN`, validasi rujukan (backlog `#56`)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from anjab_abk_backend.models import RedesainMasalahModel, RedesainRiwayatModel

URL = "/api/v1/redesain/bukti"
URL_PROSES = "/api/v1/redesain/proses"
URL_KODE = "/api/v1/redesain/kode-orang"


def _masalah_id(db_session, kode: str = "M-K01-01") -> str:
    return db_session.scalars(
        select(RedesainMasalahModel.id).where(RedesainMasalahModel.kode == kode)
    ).one()


def _tim(client_as, partisipan_factory, subject: str):
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _sekolah(client_as, label: str) -> str:
    admin = client_as(f"admin-{label}", groups=["admin"])
    npsn = str(uuid.uuid4().int)[:8]
    r = admin.post(
        "/api/v1/sekolah",
        json={
            "nama": f"SD Bukti {label} {npsn}",
            "npsn": npsn,
            "jenjang_pendidikan_id": "jp_dummy",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _langkah_id(c, masalah_id: str, sekolah_id: str) -> str:
    p = c.post(
        URL_PROSES,
        json={
            "masalah_id": masalah_id,
            "sekolah_id": sekolah_id,
            "periode": "TA 2026/27",
            "nama_proses": "Penyusunan jadwal",
        },
    )
    assert p.status_code == 201, p.text
    lk = c.post(
        f"{URL_PROSES}/{p.json()['id']}/langkah",
        json={
            "tahap": "Pengumpulan data",
            "pemicu_input": "Awal semester",
            "pelaksana": "Wakasek",
            "pekerjaan_sistem": "Spreadsheet",
            "keluaran_penerima": "Draf",
            "status_langkah": "Hipotesis",
        },
    )
    assert lk.status_code == 201, lk.text
    return lk.json()["id"]


def _bukti(masalah_id: str, **kw):
    base = {
        "masalah_id": masalah_id,
        "unit_periode": "SD A, TA 2026/27",
        "jenis": "SK/aturan",
        "independen": "Ya",
        "klaim_didukung": "Jadwal disusun manual oleh wakasek.",
        "tanggal_versi_lokasi": "SK Kepsek 12/2026, arsip TU",
    }
    base.update(kw)
    return base


def test_create_bukti_dengan_langkah_kode_default_search_dan_riwayat(
    client_as, partisipan_factory, db_session
):
    skl = _sekolah(client_as, "a")
    c = _tim(client_as, partisipan_factory, "bkt-1")
    mid = _masalah_id(db_session)
    lid = _langkah_id(c, mid, skl)

    r = c.post(URL, json=_bukti(mid, langkah_id=lid))
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["kode"] == "B-0001"
    assert b["status_pemeriksaan"] == "Belum diperiksa"
    assert b["langkah_id"] == lid

    s = c.post(f"{URL}/search", json={"domain": [["masalah_id", "=", mid]]})
    assert s.status_code == 200, s.text
    assert s.json()["total"] == 1

    assert c.get(f"{URL}/{b['id']}").json()["kode"] == "B-0001"
    assert c.get(URL).json()["total"] >= 1

    kedua = c.post(URL, json=_bukti(_masalah_id(db_session, "M-K02-01")))
    assert kedua.json()["kode"] == "B-0002"


def test_patch_status_pemeriksa_dan_riwayat_dua_baris(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "bkt-2")
    mid = _masalah_id(db_session)
    pemeriksa = c.post(URL_KODE, json={"keterangan_peran": "Narasumber pemeriksa"}).json()["kode"]
    b = c.post(URL, json=_bukti(mid)).json()

    p = c.patch(
        f"{URL}/{b['id']}",
        json={
            "status_pemeriksaan": "Diperiksa sesuai klaim",
            "pemeriksa_kode_orang": pemeriksa,
            "alasan": "Dokumen asli dicocokkan.",
        },
    )
    assert p.status_code == 200, p.text
    assert p.json()["status_pemeriksaan"] == "Diperiksa sesuai klaim"
    assert p.json()["pemeriksa_kode_orang"] == pemeriksa

    rw = RedesainRiwayatModel
    rows = db_session.scalars(
        select(rw).where(rw.entitas == "bukti", rw.entitas_id == b["id"])
    ).all()
    assert sorted(r.aksi for r in rows) == ["create", "update"]


def test_langkah_proses_masalah_lain_422(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as, "b")
    c = _tim(client_as, partisipan_factory, "bkt-3")
    lid = _langkah_id(c, _masalah_id(db_session, "M-K02-01"), skl)
    r = c.post(URL, json=_bukti(_masalah_id(db_session, "M-K01-01"), langkah_id=lid))
    assert r.status_code == 422, r.text


def test_kode_orang_tak_dikenal_dan_kosakata_422(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "bkt-4")
    mid = _masalah_id(db_session)
    assert c.post(URL, json=_bukti(mid, pembuat_kode_orang="O-9999")).status_code == 422
    assert c.post(URL, json=_bukti(mid, jenis="Rumor")).status_code == 422
    assert c.post(URL, json=_bukti(mid, independen="Ada indikasi")).status_code == 422
    assert c.post(URL, json=_bukti("tidak-ada")).status_code == 422
    ok = c.post(URL, json=_bukti(mid, status_pemeriksaan="Diperiksa sesuai klaim"))
    assert ok.status_code == 201, ok.text


def test_sekolah_pengisi_ditolak_403(client_as, partisipan_factory, db_session):
    partisipan_factory("bkt-5")
    sp = client_as("bkt-5", groups=["sekolah-pengisi"])
    assert sp.get(URL).status_code == 403
    assert sp.post(URL, json=_bukti(_masalah_id(db_session))).status_code == 403
