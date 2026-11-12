"""Tes penerima jamak dan kesiapan per periode pada alternatif redesain (backlog `#133`)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from anjab_abk_backend.models import (
    JabatanModel,
    RedesainAlternatifPenerimaModel,
    RedesainKesiapanModel,
    RedesainMasalahModel,
)
from anjab_abk_backend.redesain.schemas.alternatif import StatusKesiapan
from anjab_abk_backend.redesain.services.alternatif import hitung_status_opsi

URL = "/api/v1/redesain/alternatif"
R, C, H = StatusKesiapan.READY, StatusKesiapan.CONDITIONAL, StatusKesiapan.HOLD


# --- Unit murni: hitung_status_opsi -------------------------------------------------


@pytest.mark.parametrize(
    ("penerima", "harapan"),
    [
        ([(True, R), (True, R)], R),
        ([(True, R), (True, C)], C),
        ([(True, R), (True, None)], H),  # material belum dinilai
        ([(True, R), (False, H)], R),  # non-material HOLD tak berpengaruh
        ([(True, R), (False, None)], R),  # non-material belum dinilai tak berpengaruh
        ([(True, C), (True, H)], H),
        ([(False, C)], C),
        ([], H),  # tanpa penerima
    ],
)
def test_hitung_status_opsi(penerima, harapan):
    assert hitung_status_opsi(penerima) == harapan


# --- Integrasi ----------------------------------------------------------------------


def _jabatan(db_session) -> str:
    jid = f"jbt_{uuid.uuid4().hex[:8]}"
    db_session.add(
        JabatanModel(id=jid, kode=jid.upper(), nama=f"Jabatan {jid}", jenis="struktural")
    )
    db_session.flush()
    return jid


def _tim(client_as, partisipan_factory, subject: str):
    partisipan_factory(subject)
    return client_as(subject, groups=["tim-kajian"])


def _alternatif(c, db_session) -> str:
    mid = db_session.scalars(
        select(RedesainMasalahModel.id).where(RedesainMasalahModel.kode == "M-K01-01")
    ).one()
    r = c.post(
        URL,
        json={
            "masalah_id": mid,
            "opsi": "Sederhanakan",
            "alur_kini_vs_usulan": "Kini A; usulan B.",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _penerima(c, aid: str, jabatan_id: str, material: bool = True) -> str:
    r = c.post(
        f"{URL}/{aid}/penerima", json={"penerima_jabatan_id": jabatan_id, "material": material}
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _nilai(penerima_id: str, **kw) -> dict:
    body = {
        "penerima_id": penerima_id,
        "periode": "2026/27",
        "status": "READY",
        "delta_asal_jam": "-2.50",
        "delta_penerima_jam": "3.00",
        "delta_organisasi_jam": "0.50",
    }
    body.update(kw)
    return body


def test_dua_penerima_nilai_dan_matriks(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "kes-1")
    aid = _alternatif(c, db_session)
    p1 = _penerima(c, aid, _jabatan(db_session))
    p2 = _penerima(c, aid, _jabatan(db_session))
    assert len(c.get(f"{URL}/{aid}/penerima").json()) == 2

    # Satu READY, satu belum dinilai -> HOLD.
    assert c.post(f"{URL}/{aid}/kesiapan", json=_nilai(p1)).status_code == 201
    m = c.get(f"{URL}/{aid}/kesiapan", params={"periode": "2026/27"})
    assert m.status_code == 200, m.text
    body = m.json()
    assert body["status_opsi"] == "HOLD"
    by = {b["penerima_id"]: b for b in body["baris"]}
    assert by[p1]["status"] == "READY"
    assert by[p2]["status"] is None and by[p2]["dinilai_pada"] is None

    # Keduanya dinilai -> READY, lalu periode lain tetap HOLD.
    assert c.post(f"{URL}/{aid}/kesiapan", json=_nilai(p2)).status_code == 201
    assert (
        c.get(f"{URL}/{aid}/kesiapan", params={"periode": "2026/27"}).json()["status_opsi"]
        == "READY"
    )
    assert (
        c.get(f"{URL}/{aid}/kesiapan", params={"periode": "2027/28"}).json()["status_opsi"]
        == "HOLD"
    )


def test_not_estimable_menyimpan_null_bukan_nol(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "kes-2")
    aid = _alternatif(c, db_session)
    p = _penerima(c, aid, _jabatan(db_session))
    r = c.post(
        f"{URL}/{aid}/kesiapan",
        json=_nilai(p, delta_asal_jam=None, delta_asal_estimasi="NOT_ESTIMABLE"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["delta_asal_jam"] is None
    assert r.json()["delta_asal_estimasi"] == "NOT_ESTIMABLE"
    baris = c.get(f"{URL}/{aid}/kesiapan", params={"periode": "2026/27"}).json()["baris"][0]
    assert baris["delta_asal_jam"] is None
    assert baris["delta_asal_estimasi"] == "NOT_ESTIMABLE"
    row = db_session.scalars(
        select(RedesainKesiapanModel).where(RedesainKesiapanModel.penerima_id == p)
    ).one()
    assert row.delta_asal_jam is None


def test_koreksi_baris_baru_matriks_memakai_terakhir(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "kes-3")
    aid = _alternatif(c, db_session)
    p = _penerima(c, aid, _jabatan(db_session))
    assert c.post(f"{URL}/{aid}/kesiapan", json=_nilai(p, status="READY")).status_code == 201
    r = c.post(
        f"{URL}/{aid}/kesiapan", json=_nilai(p, status="HOLD", alasan_hold="Tenaga belum ada.")
    )
    assert r.status_code == 201, r.text
    n = db_session.scalars(
        select(RedesainKesiapanModel).where(RedesainKesiapanModel.penerima_id == p)
    ).all()
    assert len(n) == 2
    m = c.get(f"{URL}/{aid}/kesiapan", params={"periode": "2026/27"}).json()
    assert m["baris"][0]["status"] == "HOLD"
    assert m["baris"][0]["alasan_hold"] == "Tenaga belum ada."
    assert m["status_opsi"] == "HOLD"


def test_negatif_validasi_422(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "kes-4")
    aid = _alternatif(c, db_session)
    p = _penerima(c, aid, _jabatan(db_session))
    k = f"{URL}/{aid}/kesiapan"
    assert c.post(k, json=_nilai(p, status="CONDITIONAL")).status_code == 422
    assert c.post(k, json=_nilai(p, status="CONDITIONAL", syarat="  ")).status_code == 422
    assert c.post(k, json=_nilai(p, status="HOLD")).status_code == 422
    assert c.post(k, json=_nilai(p, delta_asal_estimasi="NOT_ESTIMABLE")).status_code == 422
    assert (
        c.post(k, json=_nilai(p, delta_asal_jam=None)).status_code == 422
    )  # ESTIMATED tanpa nilai
    assert c.post(k, json=_nilai(p, periode="2026-27")).status_code == 422
    assert c.post(k, json=_nilai(p, status="MAYBE")).status_code == 422
    assert c.get(k, params={"periode": "salah"}).status_code == 422
    assert c.get(k).status_code == 422  # periode wajib
    ok = c.post(k, json=_nilai(p, status="CONDITIONAL", syarat="Pelatihan dulu."))
    assert ok.status_code == 201, ok.text


def test_penerima_ganda_409_dan_jabatan_tak_dikenal_422(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "kes-5")
    aid = _alternatif(c, db_session)
    jid = _jabatan(db_session)
    _penerima(c, aid, jid)
    dup = c.post(f"{URL}/{aid}/penerima", json={"penerima_jabatan_id": jid})
    assert dup.status_code == 409, dup.text
    assert dup.json()["error"] == "PENERIMA_GANDA"
    assert c.post(f"{URL}/{aid}/penerima", json={"penerima_jabatan_id": "jbt-x"}).status_code == 422
    assert c.get(f"{URL}/tidak-ada/penerima").status_code == 404
    assert c.get(f"{URL}/tidak-ada/kesiapan", params={"periode": "2026/27"}).status_code == 404


def test_penerima_milik_alternatif_lain_422(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "kes-6")
    a1 = _alternatif(c, db_session)
    a2 = _alternatif(c, db_session)
    p2 = _penerima(c, a2, _jabatan(db_session))
    r = c.post(f"{URL}/{a1}/kesiapan", json=_nilai(p2))
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "PENERIMA_BUKAN_MILIK_ALTERNATIF"


def test_alternatif_tanpa_penerima_hold(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "kes-7")
    aid = _alternatif(c, db_session)
    m = c.get(f"{URL}/{aid}/kesiapan", params={"periode": "2026/27"}).json()
    assert m["status_opsi"] == "HOLD" and m["baris"] == []


def test_non_tim_kajian_403(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "kes-8")
    aid = _alternatif(c, db_session)
    p = _penerima(c, aid, _jabatan(db_session))
    partisipan_factory("kes-8b")
    sp = client_as("kes-8b", groups=["sekolah-pengisi"])
    assert sp.get(f"{URL}/{aid}/penerima").status_code == 403
    assert sp.post(f"{URL}/{aid}/penerima", json={"penerima_jabatan_id": "x"}).status_code == 403
    assert sp.post(f"{URL}/{aid}/kesiapan", json=_nilai(p)).status_code == 403
    assert sp.get(f"{URL}/{aid}/kesiapan", params={"periode": "2026/27"}).status_code == 403


def test_penerima_tercatat_di_db(client_as, partisipan_factory, db_session):
    c = _tim(client_as, partisipan_factory, "kes-9")
    aid = _alternatif(c, db_session)
    _penerima(c, aid, _jabatan(db_session), material=False)
    rows = db_session.scalars(
        select(RedesainAlternatifPenerimaModel).where(
            RedesainAlternatifPenerimaModel.alternatif_id == aid
        )
    ).all()
    assert len(rows) == 1 and rows[0].material is False
