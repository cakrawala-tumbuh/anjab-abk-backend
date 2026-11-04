"""Test kunci optimistik (If-Match/ETag) dan Idempotency-Key rute tulis modul redesain (#77)."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.models import (
    RedesainBuktiModel,
    RedesainKonfirmasiModel,
    RedesainKonteksModel,
    RedesainMasalahModel,
    RedesainRiwayatModel,
)
from anjab_abk_backend.services.idempotency_sql import SqlIdempotencyStore

BASE = "/api/v1/redesain"
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


def _tim(client_as, partisipan_factory):
    subject = f"tim-{uuid.uuid4().hex[:6]}"
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _sekolah(client_as) -> str:
    admin = client_as(f"admin-{uuid.uuid4().hex[:6]}", groups=["admin"])
    npsn = str(uuid.uuid4().int)[:8]
    r = admin.post(
        "/api/v1/sekolah",
        json={"nama": f"SD Conc {npsn}", "npsn": npsn, "jenjang_pendidikan_id": "jp_x"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _masalah(tim, db_session, sekolah_id: str | None = None) -> dict:
    konteks_id = db_session.scalars(
        select(RedesainKonteksModel.id).where(RedesainKonteksModel.kode == "K-01")
    ).one()
    payload = {
        "konteks_id": konteks_id,
        "periode_acuan": "TA 2026/27",
        "rumusan_hipotesis": HIPOTESIS,
        "sumber_awal_keterbatasan": "Catatan rapat; belum diverifikasi.",
        "gelombang": "G1",
    }
    if sekolah_id:
        payload["sekolah_id"] = sekolah_id
    r = tim.post(f"{BASE}/masalah", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _jumlah_riwayat(db_session, entitas: str, entitas_id: str) -> int:
    db_session.expire_all()
    return db_session.scalar(
        select(func.count())
        .select_from(RedesainRiwayatModel)
        .where(
            RedesainRiwayatModel.entitas == entitas, RedesainRiwayatModel.entitas_id == entitas_id
        )
    )


def _wajib_if_match(app):
    app.dependency_overrides[get_settings] = lambda: Settings(
        docs_enabled=True, cors_origins=[], allowed_hosts=["*"], require_if_match=True
    )


def test_patch_masalah_etag_if_match_ok_lalu_usang_412_tanpa_riwayat_baru(
    client_as, partisipan_factory, db_session
):
    tim = _tim(client_as, partisipan_factory)
    m = _masalah(tim, db_session)
    url = f"{BASE}/masalah/{m['id']}"
    etag = tim.get(url).headers["etag"]
    awal = _jumlah_riwayat(db_session, "masalah", m["id"])

    ok = tim.patch(url, json={"gelombang": "G2"}, headers={"If-Match": etag})
    assert ok.status_code == 200, ok.text
    assert ok.headers["etag"] != etag
    assert ok.headers["etag"] == tim.get(url).headers["etag"]
    assert _jumlah_riwayat(db_session, "masalah", m["id"]) == awal + 1

    usang = tim.patch(url, json={"gelombang": "G3"}, headers={"If-Match": etag})
    assert usang.status_code == 412
    assert tim.get(url).json()["gelombang"] == "G2"
    assert _jumlah_riwayat(db_session, "masalah", m["id"]) == awal + 1


def test_patch_penilaian_usang_412_dan_wajib_if_match_428(
    client_as, partisipan_factory, db_session, app
):
    tim = _tim(client_as, partisipan_factory)
    m = _masalah(tim, db_session)
    r = tim.post(
        f"{BASE}/penilaian",
        json={
            "masalah_id": m["id"],
            "status_bukti": "Diperkuat untuk klaim",
            "gap_material": "Tidak",
            "indikasi_kritis": "Tidak terlihat",
            "k1": "Sedang",
            "k2": "Rendah",
            "k3": "Tinggi",
            "k4": "Tinggi",
        },
    )
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    url = f"{BASE}/penilaian/{pid}"
    etag = tim.get(url).headers["etag"]
    assert tim.patch(url, json={"k3": "Rendah"}).status_code == 200  # tanpa header: lolos
    awal = _jumlah_riwayat(db_session, "penilaian", pid)

    usang = tim.patch(url, json={"k3": "Sedang"}, headers={"If-Match": etag})
    assert usang.status_code == 412
    assert _jumlah_riwayat(db_session, "penilaian", pid) == awal

    _wajib_if_match(app)
    try:
        assert tim.patch(url, json={"k3": "Sedang"}).status_code == 428
    finally:
        app.dependency_overrides.pop(get_settings, None)
    assert _jumlah_riwayat(db_session, "penilaian", pid) == awal


def test_post_bukti_key_sama_satu_baris_dan_satu_riwayat(client_as, partisipan_factory, db_session):
    tim = _tim(client_as, partisipan_factory)
    m = _masalah(tim, db_session)
    payload = {
        "masalah_id": m["id"],
        "unit_periode": "SD A, TA 2026/27",
        "jenis": "SK/aturan",
        "independen": "Ya",
        "klaim_didukung": "Jadwal disusun manual oleh wakasek.",
        "tanggal_versi_lokasi": "SK Kepsek 12/2026, arsip TU",
    }
    h = {"Idempotency-Key": uuid.uuid4().hex}
    pertama = tim.post(f"{BASE}/bukti", json=payload, headers=h)
    kedua = tim.post(f"{BASE}/bukti", json=payload, headers=h)
    assert pertama.status_code == 201, pertama.text
    assert kedua.status_code == 200, kedua.text
    assert kedua.json() == pertama.json()
    db_session.expire_all()
    n = db_session.scalar(
        select(func.count())
        .select_from(RedesainBuktiModel)
        .where(RedesainBuktiModel.masalah_id == m["id"])
    )
    assert n == 1
    assert _jumlah_riwayat(db_session, "bukti", pertama.json()["id"]) == 1


def test_post_status_konfirmasi_masalah_key_sama_satu_riwayat(
    client_as, partisipan_factory, db_session
):
    tim = _tim(client_as, partisipan_factory)
    m = _masalah(tim, db_session)
    url = f"{BASE}/masalah/{m['id']}/status-konfirmasi"
    awal = _jumlah_riwayat(db_session, "masalah", m["id"])
    h = {"Idempotency-Key": uuid.uuid4().hex}
    assert tim.post(url, json={"dibuka": True}, headers=h).status_code == 200
    ulang = tim.post(url, json={"dibuka": True}, headers=h)
    assert ulang.status_code == 200
    assert ulang.json()["dibuka_untuk_konfirmasi"] is True
    assert _jumlah_riwayat(db_session, "masalah", m["id"]) == awal + 1


def test_post_key_sama_masih_diproses_409(client_as, partisipan_factory, db_session):
    tim = _tim(client_as, partisipan_factory)
    m = _masalah(tim, db_session)
    url = f"{BASE}/masalah/{m['id']}/status-konfirmasi"
    assert SqlIdempotencyStore(db_session).reserve(f"POST:{url}:sibuk")
    r = tim.post(url, json={"dibuka": True}, headers={"Idempotency-Key": "sibuk"})
    assert r.status_code == 409
    assert tim.get(f"{BASE}/masalah/{m['id']}").json()["dibuka_untuk_konfirmasi"] is False


def test_konfirmasi_create_key_sama_satu_baris_update_if_match_usang_412(
    client_as, partisipan_factory, db_session
):
    skl = _sekolah(client_as)
    tim = _tim(client_as, partisipan_factory)
    m = _masalah(tim, db_session, skl)
    assert (
        tim.post(f"{BASE}/masalah/{m['id']}/status-konfirmasi", json={"dibuka": True}).status_code
        == 200
    )
    subject = f"skl-{uuid.uuid4().hex[:6]}"
    partisipan_factory(subject, sekolah_id=skl)
    pengisi = client_as(subject, groups=["sekolah-pengisi"])

    h = {"Idempotency-Key": uuid.uuid4().hex}
    pertama = pengisi.post(f"{BASE}/konfirmasi", json={"masalah_id": m["id"]}, headers=h)
    kedua = pengisi.post(f"{BASE}/konfirmasi", json={"masalah_id": m["id"]}, headers=h)
    assert pertama.status_code == 201, pertama.text
    assert kedua.status_code == 200, kedua.text
    assert kedua.json()["id"] == pertama.json()["id"]
    db_session.expire_all()
    assert (
        db_session.scalar(
            select(func.count())
            .select_from(RedesainKonfirmasiModel)
            .where(RedesainKonfirmasiModel.masalah_id == m["id"])
        )
        == 1
    )

    url = f"{BASE}/konfirmasi/{pertama.json()['id']}"
    etag = pengisi.get(url).headers["etag"]
    ok = pengisi.patch(
        url, json={"cerita_sebelum": "Cerita awal kami."}, headers={"If-Match": etag}
    )
    assert ok.status_code == 200, ok.text
    assert ok.headers["etag"] == pengisi.get(url).headers["etag"]
    usang = pengisi.patch(url, json={"cerita_sebelum": "Cerita lain."}, headers={"If-Match": etag})
    assert usang.status_code == 412
    assert pengisi.get(url).json()["cerita_sebelum"] == "Cerita awal kami."


def test_langkah_get_etag_dan_patch_usang_412(client_as, partisipan_factory, db_session):
    skl = _sekolah(client_as)
    tim = _tim(client_as, partisipan_factory)
    m = _masalah(tim, db_session, skl)
    p = tim.post(
        f"{BASE}/proses",
        json={
            "masalah_id": m["id"],
            "sekolah_id": skl,
            "periode": "TA 2026/27",
            "nama_proses": "Penyusunan jadwal",
        },
    )
    assert p.status_code == 201, p.text
    lk = tim.post(
        f"{BASE}/proses/{p.json()['id']}/langkah",
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
    url = f"{BASE}/langkah/{lk.json()['id']}"
    etag = tim.get(url).headers["etag"]
    ok = tim.patch(url, json={"pelaksana": "Kepsek"}, headers={"If-Match": etag})
    assert ok.status_code == 200, ok.text
    assert ok.headers["etag"] == tim.get(url).headers["etag"]
    assert tim.patch(url, json={"pelaksana": "TU"}, headers={"If-Match": etag}).status_code == 412
    assert tim.get(url).json()["pelaksana"] == "Kepsek"


def test_tanpa_header_perilaku_lama_tetap(client_as, partisipan_factory, db_session):
    tim = _tim(client_as, partisipan_factory)
    m = _masalah(tim, db_session)
    url = f"{BASE}/masalah/{m['id']}"
    assert tim.patch(url, json={"gelombang": "G2"}).status_code == 200
    assert tim.patch(url, json={"gelombang": "G3"}).status_code == 200
    assert db_session.get(RedesainMasalahModel, m["id"]) is not None


def test_bukti_get_etag_terkirim_sesuai_deklarasi_openapi(
    client_as, partisipan_factory, db_session
):
    tim = _tim(client_as, partisipan_factory)
    skema = tim.get("/openapi.json").json()
    resp = skema["paths"][f"{BASE}/bukti/{{bukti_id}}"]["get"]["responses"]["200"]
    assert "ETag" in resp["headers"]
    m = _masalah(tim, db_session)
    b = tim.post(
        f"{BASE}/bukti",
        json={
            "masalah_id": m["id"],
            "unit_periode": "SD A, TA 2026/27",
            "jenis": "SK/aturan",
            "independen": "Ya",
            "klaim_didukung": "Jadwal disusun manual oleh wakasek.",
            "tanggal_versi_lokasi": "SK Kepsek 12/2026, arsip TU",
        },
    )
    assert b.status_code == 201, b.text
    assert tim.get(f"{BASE}/bukti/{b.json()['id']}").headers.get("ETag")
