"""Tes uji kering gerbang PII sumber narasi: hitungan saja, tanpa tulis, tanpa nilai PII."""

from __future__ import annotations

import logging

from sqlalchemy import event
from sqlalchemy.orm import Session

from anjab_abk_backend.config import get_settings
from anjab_abk_backend.models import AiRunModel, AsyncJobModel

URL = "/api/v1/narasi/sumber"
UJI = f"{URL}/uji-kering"
EMAIL_UJI = "uji.fiktif@contoh.invalid"
NAMA_UJI = "Zxqvbn Pelita"


def _tim(client_as):
    return client_as("tim-uji-kering", groups=["tim-kajian"])


def _simpan(c, teks: str, jenis: str = "DOKUMEN_RESMI") -> str:
    r = c.post(
        URL,
        json={
            "judul": "Uji",
            "jenis": jenis,
            "versi": "v1",
            "periode": "2026/27",
            "teks": teks,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_campuran_hitungan_dan_dokumen_resmi_diperiksa_pii(client_as, partisipan_factory):
    partisipan_factory("uk-1", nama=NAMA_UJI)
    c = _tim(client_as)
    bersih = _simpan(c, "Pedoman umum tanpa data pribadi.")
    email = _simpan(c, f"Hubungi {EMAIL_UJI} untuk keterangan.")
    nama = _simpan(c, f"Disusun oleh {NAMA_UJI} pada 2026.", jenis="SINTETIS")
    r = c.post(UJI, json={"sumber_ids": [bersih, email, nama]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert (d["total"], d["lolos"], d["ditolak"]) == (3, 1, 2)
    assert d["per_alasan"] == {"PII_DITEMUKAN": 2}
    assert d["per_kategori"]["EMAIL"] == 1
    assert d["per_kategori"]["NAMA_TERDAFTAR"] >= 1
    per_id = {i["sumber_id"]: i for i in d["items"]}
    assert per_id[bersih]["lolos"] is True and per_id[bersih]["jenis"] == "DOKUMEN_RESMI"
    assert per_id[email]["alasan"] == "PII_DITEMUKAN"  # bukan JENIS_DITOLAK
    assert per_id[email]["temuan"] == {"EMAIL": 1}


def test_kata_umum_di_kamus_terhitung_nama_terdaftar(client_as, partisipan_factory):
    partisipan_factory("uk-2", nama="Rencana Kerja Sentosa")
    c = _tim(client_as)
    sid = _simpan(c, "Rencana pembelajaran tahunan disusun bersama.")
    d = c.post(UJI, json={"sumber_ids": [sid]}).json()
    assert d["ditolak"] == 1
    assert d["items"][0]["temuan"].get("NAMA_TERDAFTAR", 0) >= 1
    assert d["per_kategori"]["NAMA_TERDAFTAR"] == 1


def test_null_berarti_semua_dan_flag_mati_tetap_jalan(client_as):
    c = _tim(client_as)
    a = _simpan(c, "Satu.")
    b = _simpan(c, f"Dua {EMAIL_UJI}.")
    d = c.post(UJI, json={}).json()
    ids = {i["sumber_id"] for i in d["items"]}
    assert {a, b} <= ids
    assert d["total"] == len(d["items"])


def test_tanpa_tulisan_dan_settings_tak_berubah(client_as, db_session: Session):
    c = _tim(client_as)
    sid = _simpan(c, f"Surel {EMAIL_UJI}.")
    sebelum = get_settings().model_dump()
    ai_run, job = db_session.query(AiRunModel).count(), db_session.query(AsyncJobModel).count()
    ditulis: list[str] = []

    def _catat(session, _ctx, _inst):
        ditulis.extend(type(o).__name__ for o in (*session.new, *session.dirty, *session.deleted))

    event.listen(db_session, "before_flush", _catat)
    try:
        assert c.post(UJI, json={"sumber_ids": [sid]}).status_code == 200
    finally:
        event.remove(db_session, "before_flush", _catat)
    assert ditulis == []
    assert db_session.query(AiRunModel).count() == ai_run
    assert db_session.query(AsyncJobModel).count() == job
    assert get_settings().model_dump() == sebelum


def test_respons_dan_log_tanpa_nilai_pii(client_as, partisipan_factory, caplog):
    partisipan_factory("uk-3", nama=NAMA_UJI)
    c = _tim(client_as)
    sid = _simpan(c, f"{EMAIL_UJI} dan {NAMA_UJI} menghadiri rapat.")
    with caplog.at_level(logging.DEBUG):
        r = c.post(UJI, json={"sumber_ids": [sid]})
    assert r.status_code == 200
    gabung = r.text + "\n".join(f"{x.getMessage()} {x.__dict__}" for x in caplog.records)
    assert EMAIL_UJI not in gabung
    assert "Zxqvbn" not in gabung
    assert "menghadiri rapat" not in gabung


def test_terlalu_banyak_dan_id_tak_dikenal_422(client_as):
    c = _tim(client_as)
    r = c.post(UJI, json={"sumber_ids": [f"id-{i}" for i in range(501)]})
    assert r.status_code == 422
    assert r.json()["error"] == "uji_kering_terlalu_banyak"
    assert c.post(UJI, json={"sumber_ids": ["tidak-ada"]}).status_code == 422


def test_bukan_tim_kajian_403_tanpa_token_401(client_as, anon_client):
    assert client_as("adm", groups=["admin"]).post(UJI, json={}).status_code == 403
    assert anon_client.post(UJI, json={}).status_code == 401
