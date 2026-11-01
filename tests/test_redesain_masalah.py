"""Tes masalah redesain + seed 8 hipotesis awal (backlog `#51`)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from anjab_abk_backend.models import (
    RedesainKonteksModel,
    RedesainMasalahModel,
    RedesainMasalahUraianTugasModel,
    TiUraianTugasModel,
)
from anjab_abk_backend.redesain.seed import seed_masalah

URL = "/api/v1/redesain/masalah"


def _konteks_id(db_session, kode: str = "K-01") -> str:
    return db_session.scalars(
        select(RedesainKonteksModel.id).where(RedesainKonteksModel.kode == kode)
    ).one()


def _uraian_ids(db_session, n: int = 2) -> list[str]:
    return list(
        db_session.scalars(
            select(TiUraianTugasModel.id).order_by(TiUraianTugasModel.id).limit(n)
        ).all()
    )


def _payload(konteks_id: str, **kw):
    base = {
        "konteks_id": konteks_id,
        "periode_acuan": "TA 2026/27",
        "rumusan_hipotesis": "Dugaan uji",
        "sumber_awal_keterbatasan": "Sumber uji",
        "gelombang": "G3",
    }
    base.update(kw)
    return base


def _count(db_session, model) -> int:
    return db_session.scalar(select(func.count()).select_from(model))


def _tim(client_as, partisipan_factory, subject: str):
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def test_seed_dua_kali_tepat_8_hipotesis(db_session):
    assert seed_masalah(db_session) == 0
    assert seed_masalah(db_session) == 0
    rows = db_session.scalars(select(RedesainMasalahModel)).all()
    assert len(rows) == 8
    assert {r.status_awal for r in rows} == {"Hipotesis"}
    assert all(r.sekolah_id is None for r in rows)
    assert all(r.periode_pasti is False for r in rows)
    k0103 = next(r for r in rows if r.kode == "M-K01-03")
    assert k0103.keterangan_sekolah == "Sumber contoh TK Semarang"


def test_search_gelombang_g2_satu_baris(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "tkm-1")
    r = c.post(f"{URL}/search", json={"domain": [["gelombang", "=", "G2"]]})
    assert r.status_code == 200
    assert [i["kode"] for i in r.json()["items"]] == ["M-K05-01"]
    assert c.get(URL).json()["total"] == 8


def test_create_kode_berikutnya_sekolah_uraian_dan_riwayat(
    client_as, partisipan_factory, db_session
):
    admin = client_as("admin-m", groups=["admin"])
    npsn = str(uuid.uuid4().int)[:8]
    skl = admin.post(
        "/api/v1/sekolah",
        json={"nama": f"SD Masalah {npsn}", "npsn": npsn, "jenjang_pendidikan_id": "jp_dummy"},
    )
    assert skl.status_code == 201
    ut = _uraian_ids(db_session, 2)
    c = _tim(client_as, partisipan_factory, "tkm-2")
    r = c.post(
        URL,
        json=_payload(
            _konteks_id(db_session), sekolah_id=skl.json()["id"], uraian_tugas_ids=[ut[0]]
        ),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kode"] == "M-K01-04"
    assert body["status_awal"] == "Hipotesis"
    assert body["status_awal_dibekukan_pada"] is None
    got = c.get(f"{URL}/{body['id']}").json()
    assert got["uraian_tugas_ids"] == [ut[0]]
    assert got["sekolah_id"] == skl.json()["id"]
    rw = c.get("/api/v1/redesain/riwayat", params={"entitas_id": body["id"]}).json()
    assert rw["total"] == 1 and rw["items"][0]["entitas"] == "masalah"

    # ganti-penuh tautan uraian tugas
    p = c.patch(f"{URL}/{body['id']}", json={"uraian_tugas_ids": [ut[1]]})
    assert p.status_code == 200, p.text
    assert p.json()["uraian_tugas_ids"] == [ut[1]]
    assert c.post(URL, json=_payload(_konteks_id(db_session))).json()["kode"] == "M-K01-05"


def test_status_konfirmasi_buka_tutup(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "tkm-3")
    m = c.post(f"{URL}/search", json={"domain": [["kode", "=", "M-K02-01"]]}).json()["items"][0]
    assert m["dibuka_untuk_konfirmasi"] is False
    r = c.post(f"{URL}/{m['id']}/status-konfirmasi", json={"dibuka": True})
    assert r.status_code == 200
    assert r.json()["dibuka_untuk_konfirmasi"] is True
    cari = c.post(f"{URL}/search", json={"domain": [["dibuka_untuk_konfirmasi", "=", True]]})
    assert [i["kode"] for i in cari.json()["items"]] == ["M-K02-01"]
    r = c.post(f"{URL}/{m['id']}/status-konfirmasi", json={"dibuka": False})
    assert r.json()["dibuka_untuk_konfirmasi"] is False
    rw = c.get("/api/v1/redesain/riwayat", params={"entitas_id": m["id"]}).json()
    assert [i["aksi"] for i in rw["items"]].count("status-konfirmasi") == 2


def test_status_awal_beku_patch_409_field_lain_200(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "tkm-4")
    m = c.post(f"{URL}/search", json={"domain": [["kode", "=", "M-K03-01"]]}).json()["items"][0]
    rec = db_session.get(RedesainMasalahModel, m["id"])
    rec.status_awal_dibekukan_pada = datetime.now(UTC)
    db_session.flush()
    r = c.patch(f"{URL}/{m['id']}", json={"status_awal": "Keterangan kasus"})
    assert r.status_code == 409
    assert "dibekukan" in r.text
    r = c.patch(f"{URL}/{m['id']}", json={"penjelasan_alternatif": "Periksa ulang"})
    assert r.status_code == 200
    assert r.json()["penjelasan_alternatif"] == "Periksa ulang"
    assert r.json()["status_awal"] == "Hipotesis"


def test_status_awal_belum_beku_boleh_diubah(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "tkm-5")
    m = c.post(f"{URL}/search", json={"domain": [["kode", "=", "M-K04-01"]]}).json()["items"][0]
    r = c.patch(f"{URL}/{m['id']}", json={"status_awal": "Diperselisihkan"})
    assert r.status_code == 200
    assert r.json()["status_awal"] == "Diperselisihkan"
    assert r.json()["kode"] == "M-K04-01"


def test_uraian_tak_dikenal_422_tanpa_baris(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "tkm-6")
    sebelum_m = _count(db_session, RedesainMasalahModel)
    sebelum_r = _count(db_session, RedesainMasalahUraianTugasModel)
    ut = _uraian_ids(db_session, 1)
    r = c.post(
        URL, json=_payload(_konteks_id(db_session), uraian_tugas_ids=[ut[0], "ut_tidak_ada"])
    )
    assert r.status_code == 422
    assert "ut_tidak_ada" in r.text
    assert _count(db_session, RedesainMasalahModel) == sebelum_m
    assert _count(db_session, RedesainMasalahUraianTugasModel) == sebelum_r


def test_negatif_konteks_sekolah_404_dan_akses(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "tkm-7")
    assert c.post(URL, json=_payload("tidak-ada")).status_code == 422
    assert (
        c.post(URL, json=_payload(_konteks_id(db_session), sekolah_id="skl_x")).status_code == 422
    )
    assert c.post(URL, json=_payload(_konteks_id(db_session), kode="M-X")).status_code == 422
    assert c.get(f"{URL}/zzz").status_code == 404
    assert c.patch(f"{URL}/zzz", json={"periode_acuan": "x"}).status_code == 404
    assert c.post(f"{URL}/zzz/status-konfirmasi", json={"dibuka": True}).status_code == 404
    assert c.delete(f"{URL}/zzz").status_code == 405
    partisipan_factory("spm-1")
    assert client_as("spm-1", groups=["sekolah-pengisi"]).get(URL).status_code == 403
    assert client_as("spm-1", groups=["admin"]).get(URL).status_code == 403
