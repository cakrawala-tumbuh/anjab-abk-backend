"""Tes catatan versi metode redesain: seed 5 baris v1.3, CRUD+search Tim, riwayat (#64)."""

from __future__ import annotations

from sqlalchemy import func, select

from anjab_abk_backend.models import RedesainRiwayatModel, RedesainVersiMetodeModel
from anjab_abk_backend.redesain.seed import seed_versi_metode

URL = "/api/v1/redesain/versi-metode"


def _tim(client_as, partisipan_factory, subject: str):
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _payload(**kw) -> dict:
    base = {
        "versi": "v1.4",
        "tanggal": "2026-12-01",
        "bagian": "Ambang triase",
        "apa_diperbarui": "Ambang P1-P3 disesuaikan.",
        "alasan_risiko": "Menyesuaikan hasil uji.",
        "status_hasil_uji": "Belum diuji.",
        "pemeriksa_pemutus": "Pimpinan metode",
    }
    return {**base, **kw}


def _riwayat(db_session, entitas_id: str, aksi: str) -> int:
    r = RedesainRiwayatModel
    return db_session.scalar(
        select(func.count())
        .select_from(r)
        .where(r.entitas == "versi_metode", r.entitas_id == entitas_id, r.aksi == aksi)
    )


def test_seed_idempoten_lima_baris_v13(db_session):
    seed_versi_metode(db_session)
    assert seed_versi_metode(db_session) == 0
    m = RedesainVersiMetodeModel
    assert db_session.scalar(select(func.count()).select_from(m).where(m.versi == "v1.3")) == 5
    assert db_session.scalar(select(func.count()).select_from(m)) == 5


def test_search_bagian_satu_baris(client_as, partisipan_factory, db_session):
    seed_versi_metode(db_session)
    c = _tim(client_as, partisipan_factory, "vm-1")
    r = c.post(f"{URL}/search", json={"domain": [["bagian", "=", "Batas keputusan"]]})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["tanggal"] == "2026-10-31"
    assert c.get(URL).json()["total"] == 5


def test_create_patch_riwayat_dua_baris(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "vm-2")
    r = c.post(URL, json=_payload())
    assert r.status_code == 201, r.text
    vid = r.json()["id"]
    p = c.patch(f"{URL}/{vid}", json={"status_hasil_uji": "Lulus uji pengguna."})
    assert p.status_code == 200, p.text
    assert p.json()["status_hasil_uji"] == "Lulus uji pengguna."
    assert c.get(f"{URL}/{vid}").json()["versi"] == "v1.4"
    assert _riwayat(db_session, vid, "create") + _riwayat(db_session, vid, "update") == 2


def test_pasangan_ganda_409(client_as, partisipan_factory, db_session):
    seed_versi_metode(db_session)
    c = _tim(client_as, partisipan_factory, "vm-3")
    r = c.post(URL, json=_payload(versi="v1.3", bagian="Register"))
    assert r.status_code == 409, r.text


def test_patch_jadi_bentrok_409(client_as, partisipan_factory, db_session):
    seed_versi_metode(db_session)
    c = _tim(client_as, partisipan_factory, "vm-4")
    vid = c.post(URL, json=_payload()).json()["id"]
    r = c.patch(f"{URL}/{vid}", json={"versi": "v1.3", "bagian": "Register"})
    assert r.status_code == 409, r.text


def test_get_tak_ada_404_dan_payload_tak_valid_422(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "vm-5")
    assert c.get(f"{URL}/tidak-ada").status_code == 404
    assert c.post(URL, json=_payload(tanggal="bukan-tanggal")).status_code == 422
    assert c.post(URL, json={**_payload(), "kolom_asing": 1}).status_code == 422


def test_sekolah_pengisi_ditolak_403(client_as, partisipan_factory):
    partisipan_factory("vm-6")
    sp = client_as("vm-6", groups=["sekolah-pengisi"])
    assert sp.get(URL).status_code == 403
    assert sp.post(URL, json=_payload()).status_code == 403
    assert sp.post(f"{URL}/search", json={"domain": []}).status_code == 403
    assert sp.get(f"{URL}/x").status_code == 403
    assert sp.patch(f"{URL}/x", json={"versi": "v9"}).status_code == 403
