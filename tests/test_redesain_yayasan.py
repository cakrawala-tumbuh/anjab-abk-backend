"""Tes ringkasan yayasan (read-model masalah + penilaian): turunan, null, search, 403/404 (#62)."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select

from anjab_abk_backend.models import RedesainKodeOrangModel, RedesainMasalahModel
from anjab_abk_backend.redesain.schemas.penilaian import hari_ini_wib

URL = "/api/v1/redesain/yayasan"
PNL = "/api/v1/redesain/penilaian"


def _tim(client_as, partisipan_factory, subject: str):
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _masalah_id(db_session, kode: str = "M-K01-01") -> str:
    return db_session.scalars(
        select(RedesainMasalahModel.id).where(RedesainMasalahModel.kode == kode)
    ).one()


def _nilai(mid: str, **kw):
    base = {
        "masalah_id": mid,
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


def test_semua_masalah_muncul_dan_yang_dinilai_memuat_keputusan_serta_pemutus(
    client_as, partisipan_factory, db_session
):
    c = _tim(client_as, partisipan_factory, "yys-1")
    jumlah = db_session.scalar(select(func.count()).select_from(RedesainMasalahModel))
    assert jumlah >= 8
    r = c.get(URL, params={"limit": 100})
    assert r.status_code == 200, r.text
    assert r.json()["total"] == jumlah

    mid = _masalah_id(db_session)
    db_session.add(RedesainKodeOrangModel(id=str(uuid.uuid4()), kode="O-9301"))
    db_session.flush()
    pid = c.post(PNL, json=_nilai(mid)).json()["id"]
    put = c.post(
        f"{PNL}/{pid}/putuskan",
        json={
            "prioritas_final": "P1 - Utama",
            "alasan_final": "Dampak besar.",
            "pemutus_kode_orang": "O-9301",
            "pemutus_jabatan": "Ketua Tim Kajian",
            "tanggal_keputusan": hari_ini_wib().isoformat(),
        },
    )
    assert put.status_code == 200, put.text

    # Perubahan lewat `putuskan` langsung tampak di detail (tanpa input kedua).
    d = c.get(f"{URL}/{mid}")
    assert d.status_code == 200, d.text
    j = d.json()
    assert j["prioritas_final"] == "P1 - Utama"
    assert re.fullmatch(r"O-\d{4} — Ketua Tim Kajian", j["pemutus"])
    assert j["masalah_kode"] == "M-K01-01"
    assert j["konteks_kode"] == "K-01"
    assert j["saran_otomatis"] == "P1 - Utama"
    # Tidak memuat isi konfirmasi per orang maupun nama/email.
    for terlarang in ("cerita_sebelum", "koreksi", "nama", "email"):
        assert terlarang not in j


def test_masalah_tanpa_penilaian_field_penilaian_null(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "yys-2")
    mid = _masalah_id(db_session, "M-K02-01")
    j = c.get(f"{URL}/{mid}").json()
    for f in (
        "status_bukti",
        "k1",
        "k2",
        "k3",
        "k4",
        "indikasi_kritis",
        "saran_otomatis",
        "prioritas_final",
        "alasan_final",
        "pemutus",
        "status_penilaian",
        "tanggal_keputusan",
    ):
        assert j[f] is None, f
    assert j["peringatan"] == []
    assert isinstance(j["proses_kode"], list)


def test_search_saran_otomatis_hanya_baris_berpenilaian(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "yys-3")
    mid = _masalah_id(db_session)
    p = c.post(PNL, json=_nilai(mid, status_bukti="Hipotesis")).json()
    saran = p["saran_otomatis"]
    assert saran
    s = c.post(f"{URL}/search", json={"domain": [["saran_otomatis", "=", saran]]})
    assert s.status_code == 200, s.text
    assert [x["masalah_id"] for x in s.json()["items"]] == [mid]
    assert s.json()["total"] == 1
    k = c.post(f"{URL}/search", json={"domain": [["konteks_kode", "=", "K-01"]]})
    assert k.status_code == 200, k.text
    assert mid in [x["masalah_id"] for x in k.json()["items"]]
    bad = c.post(f"{URL}/search", json={"domain": [["rumusan_hipotesis", "=", "x"]]})
    assert bad.status_code == 422


def test_detail_id_acak_404(client_as, partisipan_factory):
    c = _tim(client_as, partisipan_factory, "yys-4")
    assert c.get(f"{URL}/{uuid.uuid4()}").status_code == 404


def test_sekolah_pengisi_ditolak_403(client_as, partisipan_factory, db_session):
    partisipan_factory("yys-5")
    sp = client_as("yys-5", groups=["sekolah-pengisi"])
    assert sp.get(URL).status_code == 403
    assert sp.post(f"{URL}/search", json={"domain": []}).status_code == 403
    assert sp.get(f"{URL}/{_masalah_id(db_session)}").status_code == 403
