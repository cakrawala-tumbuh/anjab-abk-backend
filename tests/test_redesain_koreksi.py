"""Tes alur sekolah & koreksi langkah append-only redesain (backlog `#54`)."""

from __future__ import annotations

import uuid

from sqlalchemy import select

from anjab_abk_backend.models import (
    RedesainKonteksModel,
    RedesainLangkahModel,
    RedesainProsesModel,
    RedesainRiwayatModel,
)

URL_KONF = "/api/v1/redesain/konfirmasi"
URL_LANGKAH = "/api/v1/redesain/langkah"
URL_PROSES = "/api/v1/redesain/proses"


def _sekolah(client_as, label: str) -> str:
    admin = client_as(f"admin-{label}", groups=["admin"])
    npsn = str(uuid.uuid4().int)[:8]
    r = admin.post(
        "/api/v1/sekolah",
        json={"nama": f"SD Kor {label} {npsn}", "npsn": npsn, "jenjang_pendidikan_id": "jp_x"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _tim(client_as, partisipan_factory):
    """Klien Tim; fungsi pemanggil ulang tiap kali (client_as menimpa identitas level app)."""
    subject = f"tim-{uuid.uuid4().hex[:6]}"
    partisipan_factory(subject)
    return lambda: client_as(subject, groups=["tim-kajian"])


def _pengisi(client_as, partisipan_factory, sekolah_id: str):
    subject = f"skl-{uuid.uuid4().hex[:6]}"
    partisipan_factory(subject, sekolah_id=sekolah_id)
    return client_as(subject, groups=["sekolah-pengisi"])


def _masalah(tim, db_session, sekolah_id: str) -> str:
    konteks_id = db_session.scalars(
        select(RedesainKonteksModel.id).where(RedesainKonteksModel.kode == "K-01")
    ).one()
    r = tim.post(
        "/api/v1/redesain/masalah",
        json={
            "konteks_id": konteks_id,
            "sekolah_id": sekolah_id,
            "periode_acuan": "TA 2026/27",
            "rumusan_hipotesis": "Jadwal disusun manual.",
            "sumber_awal_keterbatasan": "Catatan rapat.",
            "gelombang": "G1",
        },
    )
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    b = tim.post(f"/api/v1/redesain/masalah/{mid}/status-konfirmasi", json={"dibuka": True})
    assert b.status_code == 200, b.text
    return mid


def _proses_langkah(tim, masalah_id: str, sekolah_id: str, nama: str) -> tuple[str, str]:
    p = tim.post(
        URL_PROSES,
        json={
            "masalah_id": masalah_id,
            "sekolah_id": sekolah_id,
            "periode": "TA 2026/27",
            "nama_proses": nama,
        },
    )
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    lk = tim.post(
        f"{URL_PROSES}/{pid}/langkah",
        json={
            "tahap": f"Tahap {nama}",
            "pemicu_input": "Awal semester",
            "pelaksana": "Wakil Kepala Sekolah",
            "pekerjaan_sistem": "Spreadsheet",
            "keluaran_penerima": "Draf",
            "status_langkah": "Hipotesis",
        },
    )
    assert lk.status_code == 201, lk.text
    return pid, lk.json()["id"]


def _konfirmasi(pengisi, masalah_id: str, *, tampil: bool) -> str:
    kid = pengisi.post(URL_KONF, json={"masalah_id": masalah_id}).json()["id"]
    if tampil:
        assert (
            pengisi.patch(f"{URL_KONF}/{kid}", json={"cerita_sebelum": "Cerita kami."}).status_code
            == 200
        )
        assert pengisi.post(f"{URL_KONF}/{kid}/kunci-cerita").status_code == 200
        assert pengisi.post(f"{URL_KONF}/{kid}/tampilkan-dugaan").status_code == 200
    return kid


def test_alur_409_sebelum_dugaan_lalu_hanya_proses_sekolah_sendiri(
    client_as, partisipan_factory, db_session
):
    a = _sekolah(client_as, "a")
    b = _sekolah(client_as, "b")
    tim = _tim(client_as, partisipan_factory)
    masalah_a = _masalah(tim(), db_session, a)
    masalah_b = _masalah(tim(), db_session, b)
    pid_a, _ = _proses_langkah(tim(), masalah_a, a, "Jadwal A")
    pid_b, _ = _proses_langkah(tim(), masalah_b, b, "Jadwal B")
    # Proses sekolah B yang menempel pada masalah A (di luar jalur service) -> tak boleh ikut.
    asing = RedesainProsesModel(
        id=str(uuid.uuid4()),
        kode="PX-ASING",
        masalah_id=masalah_a,
        sekolah_id=b,
        periode="TA 2026/27",
        nama_proses="Proses sekolah lain",
    )
    db_session.add(asing)
    db_session.flush()

    pengisi_a = _pengisi(client_as, partisipan_factory, a)
    kid = _konfirmasi(pengisi_a, masalah_a, tampil=False)

    belum = pengisi_a.get(f"{URL_KONF}/{kid}/alur")
    assert belum.status_code == 409, belum.text
    assert belum.json()["error"] == "DUGAAN_BELUM_DITAMPILKAN"

    pengisi_a.patch(f"{URL_KONF}/{kid}", json={"cerita_sebelum": "Cerita."})
    pengisi_a.post(f"{URL_KONF}/{kid}/kunci-cerita")
    pengisi_a.post(f"{URL_KONF}/{kid}/tampilkan-dugaan")

    ok = pengisi_a.get(f"{URL_KONF}/{kid}/alur")
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert [p["id"] for p in body["proses"]] == [pid_a]
    assert pid_b not in ok.text and asing.id not in ok.text
    assert body["proses"][0]["langkah"][0]["tahap"] == "Tahap Jadwal A"

    lain = _pengisi(client_as, partisipan_factory, a)
    assert lain.get(f"{URL_KONF}/{kid}/alur").status_code == 403


def test_koreksi_sekolah_tersimpan_langkah_tak_berubah_tim_membaca(
    client_as, partisipan_factory, db_session
):
    a = _sekolah(client_as, "c")
    tim = _tim(client_as, partisipan_factory)
    masalah = _masalah(tim(), db_session, a)
    _, lid = _proses_langkah(tim(), masalah, a, "Jadwal")
    pengisi = _pengisi(client_as, partisipan_factory, a)
    kid = _konfirmasi(pengisi, masalah, tampil=True)

    sebelum = db_session.get(RedesainLangkahModel, lid)
    snap = (sebelum.tahap, sebelum.pelaksana, sebelum.status_langkah, sebelum.updated_at)

    r = pengisi.post(
        f"{URL_LANGKAH}/{lid}/koreksi", json={"isi": "Kami juga pakai WA.", "konfirmasi_id": kid}
    )
    assert r.status_code == 201, r.text
    assert r.json()["konfirmasi_id"] == kid
    kode_pengisi = r.json()["kode_orang"]

    t = tim().post(f"{URL_LANGKAH}/{lid}/koreksi", json={"isi": "Catatan Tim."})
    assert t.status_code == 201, t.text
    assert t.json()["konfirmasi_id"] is None

    daftar = tim().get(f"{URL_LANGKAH}/{lid}/koreksi")
    assert daftar.status_code == 200, daftar.text
    items = daftar.json()["items"]
    assert len(items) == 2 and daftar.json()["total"] == 2
    assert items[0]["kode_orang"] == kode_pengisi and items[0]["isi"] == "Kami juga pakai WA."
    assert items[0]["waktu"] <= items[1]["waktu"]

    db_session.expire_all()
    sesudah = db_session.get(RedesainLangkahModel, lid)
    assert (sesudah.tahap, sesudah.pelaksana, sesudah.status_langkah, sesudah.updated_at) == snap

    rw = RedesainRiwayatModel
    rows = db_session.scalars(
        select(rw).where(rw.entitas == "koreksi_langkah", rw.entitas_id == r.json()["id"])
    ).all()
    assert [x.aksi for x in rows] == ["create"]


def test_koreksi_negatif_akses_dan_validasi(client_as, partisipan_factory, db_session):
    a = _sekolah(client_as, "d")
    b = _sekolah(client_as, "e")
    tim = _tim(client_as, partisipan_factory)
    masalah_a = _masalah(tim(), db_session, a)
    masalah_b = _masalah(tim(), db_session, b)
    _, lid_a = _proses_langkah(tim(), masalah_a, a, "Jadwal A")
    _, lid_b = _proses_langkah(tim(), masalah_b, b, "Jadwal B")
    pengisi = _pengisi(client_as, partisipan_factory, a)
    kid = _konfirmasi(pengisi, masalah_a, tampil=True)

    # langkah proses sekolah B dengan konfirmasi sekolah A -> 403
    salah = pengisi.post(f"{URL_LANGKAH}/{lid_b}/koreksi", json={"isi": "x", "konfirmasi_id": kid})
    assert salah.status_code == 403
    # tanpa konfirmasi_id -> 403
    assert pengisi.post(f"{URL_LANGKAH}/{lid_a}/koreksi", json={"isi": "x"}).status_code == 403
    # pengisi tak boleh membaca koreksi -> 403
    assert pengisi.get(f"{URL_LANGKAH}/{lid_a}/koreksi").status_code == 403
    # isi kosong -> 422
    assert (
        pengisi.post(
            f"{URL_LANGKAH}/{lid_a}/koreksi", json={"isi": "   ", "konfirmasi_id": kid}
        ).status_code
        == 422
    )
    assert tim().post(f"{URL_LANGKAH}/{lid_a}/koreksi", json={"isi": ""}).status_code == 422
    # dugaan belum tampil -> 409
    pengisi2 = _pengisi(client_as, partisipan_factory, a)
    kid2 = _konfirmasi(pengisi2, masalah_a, tampil=False)
    belum = pengisi2.post(
        f"{URL_LANGKAH}/{lid_a}/koreksi", json={"isi": "x", "konfirmasi_id": kid2}
    )
    assert belum.status_code == 409
    assert belum.json()["error"] == "DUGAAN_BELUM_DITAMPILKAN"
    # langkah tak ada -> 404
    assert tim().post(f"{URL_LANGKAH}/tidak-ada/koreksi", json={"isi": "x"}).status_code == 404


def test_openapi_koreksi_tanpa_patch_put_delete():
    from anjab_abk_backend.main import create_app

    paths = create_app().openapi()["paths"]
    p = paths["/api/v1/redesain/langkah/{langkah_id}/koreksi"]
    assert set(p) == {"get", "post"}
