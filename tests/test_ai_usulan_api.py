"""Tes rute baca usulan AI (`/api/v1/ai/usulan`): Tim Kajian saja, daftar tanpa isi.

Seluruh data sintetis; tidak ada panggilan model. Baris `ai_usulan` dibuat langsung agar
penanda pada `isi`, `amplop`, `masukan`, dan `keluaran` run dapat dilacak ke respons dan log.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from anjab_abk_backend.models import AiRunModel, AiUsulanModel
from anjab_abk_backend.schemas.ai_run import AiRunRead
from anjab_abk_backend.schemas.ai_usulan import AiUsulanRead, AiUsulanRingkas

URL = "/api/v1/ai/usulan"
PENANDA_ISI = "ISI-RAHASIA-SINTETIS-7731"
PENANDA_AMPLOP = "AMPLOP-RAHASIA-SINTETIS-4419"
PENANDA_MASUKAN = "MASUKAN-RAHASIA-SINTETIS-2208"
PENANDA_KELUARAN = "KELUARAN-RAHASIA-SINTETIS-9054"
_DASAR = datetime(2026, 11, 1, tzinfo=UTC)
# Himpunan LITERAL (bukan `model_fields`): sembilan field #102 + `putusan_terakhir` (#103).
KUNCI_RINGKAS = {
    "id",
    "fungsi",
    "sasaran_jenis",
    "sasaran_id",
    "job_id",
    "created_at",
    "diserap_at",
    "hasil_serap",
    "kode_serap",
    "putusan_terakhir",
}
# Lima belas field detail + `putusan_terakhir` + `putusan` (#103) + `konteks_server` (#125).
KUNCI_DETAIL = KUNCI_RINGKAS | {
    "ai_run_id",
    "sumber_ids",
    "diminta_oleh",
    "isi",
    "amplop",
    "output_hash",
    "putusan",
    "konteks_server",
}


def _tim(client_as, subject: str = "tim-1"):
    return client_as(subject, groups=["tim-kajian"])


def _usulan(
    db: Session,
    *,
    fungsi: str = "P09",
    sasaran_id: str | None = None,
    sasaran_jenis: str = "NARASI_KASUS",
    hasil_serap: str | None = "USULAN_DIBUAT",
    menit: int = 0,
) -> AiUsulanModel:
    run_id = str(uuid.uuid4())
    db.add(
        AiRunModel(
            id=run_id,
            fungsi=fungsi,
            prompt_version="v1",
            prompt_hash="a" * 64,
            model_diminta="model-uji",
            protocol_id="uji",
            input_snapshot_id="b" * 64,
            sumber=[],
            masukan={"teks": PENANDA_MASUKAN},
            keluaran={"teks": PENANDA_KELUARAN},
            status_qa="LOLOS",
            kode_qa=[],
        )
    )
    db.flush()
    diserap = hasil_serap is not None
    rec = AiUsulanModel(
        id=str(uuid.uuid4()),
        fungsi=fungsi,
        sasaran_jenis=sasaran_jenis,
        sasaran_id=sasaran_id or str(uuid.uuid4()),
        job_id=str(uuid.uuid4()),
        ai_run_id=run_id,
        sumber_ids=["s1"],
        diminta_oleh="tim-1",
        created_at=_DASAR + timedelta(minutes=menit),
        diserap_at=_DASAR if diserap else None,
        hasil_serap=hasil_serap,
        kode_serap=["SUMBER_KOSONG"] if hasil_serap == "MANUAL" else None,
        isi={"ringkasan": PENANDA_ISI} if diserap else None,
        amplop={"catatan": PENANDA_AMPLOP} if diserap else None,
        output_hash="c" * 64 if diserap else None,
    )
    db.add(rec)
    db.flush()
    return rec


def _tanpa_identitas(teks: str, rec: AiUsulanModel) -> None:
    """Teks respons daftar tidak memuat pemohon maupun id run fixture."""
    assert rec.diminta_oleh not in teks
    assert rec.ai_run_id not in teks


def test_detail_memuat_isi_amplop_dan_hash(client_as, db_session):
    rec = _usulan(db_session)
    r = _tim(client_as).get(f"{URL}/{rec.id}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == KUNCI_DETAIL
    assert d["ai_run_id"] == rec.ai_run_id and d["diminta_oleh"] == "tim-1"
    assert d["isi"] == {"ringkasan": PENANDA_ISI}
    assert d["amplop"] == {"catatan": PENANDA_AMPLOP}
    assert d["output_hash"] == "c" * 64
    assert d["sumber_ids"] == ["s1"]
    assert d["job_id"] == rec.job_id
    assert d["hasil_serap"] == "USULAN_DIBUAT"
    assert d["diserap_at"] is not None
    # masukan/keluaran run tidak pernah terbuka lewat detail
    assert PENANDA_MASUKAN not in r.text
    assert PENANDA_KELUARAN not in r.text
    assert "masukan" not in d and "keluaran" not in d


def test_detail_usulan_belum_diserap_isi_null(client_as, db_session):
    rec = _usulan(db_session, hasil_serap=None)
    d = _tim(client_as).get(f"{URL}/{rec.id}").json()
    assert d["isi"] is None and d["amplop"] is None and d["output_hash"] is None
    assert d["diserap_at"] is None and d["hasil_serap"] is None


def test_id_tak_dikenal_404(client_as):
    assert _tim(client_as).get(f"{URL}/{uuid.uuid4()}").status_code == 404


def test_list_filter_dan_tanpa_isi(client_as, db_session):
    sid = str(uuid.uuid4())
    a = _usulan(db_session, fungsi="P09", sasaran_id=sid, menit=1)
    _usulan(db_session, fungsi="P10", sasaran_id=sid, menit=2)
    _usulan(db_session, fungsi="P09", menit=3)
    c = _tim(client_as)
    r = c.get(URL, params={"fungsi": "P09", "sasaran_id": sid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    assert [i["id"] for i in body["items"]] == [a.id]
    assert set(body["items"][0]) == KUNCI_RINGKAS
    for kunci in ("isi", "amplop", "output_hash", "ai_run_id", "sumber_ids", "diminta_oleh"):
        assert kunci not in body["items"][0]
    _tanpa_identitas(r.text, a)
    assert PENANDA_ISI not in r.text and PENANDA_AMPLOP not in r.text
    assert PENANDA_MASUKAN not in r.text and PENANDA_KELUARAN not in r.text


def test_list_filter_hasil_serap_urutan_dan_paging_di_sql(client_as, db_session):
    sid = str(uuid.uuid4())
    u1 = _usulan(db_session, sasaran_id=sid, menit=1, hasil_serap="MANUAL")
    u2 = _usulan(db_session, sasaran_id=sid, menit=2, hasil_serap="MANUAL")
    u3 = _usulan(db_session, sasaran_id=sid, menit=3, hasil_serap="EVIDENCE_GAP")
    c = _tim(client_as)
    r = c.get(URL, params={"sasaran_id": sid, "hasil_serap": "MANUAL"})
    assert [i["id"] for i in r.json()["items"]] == [u2.id, u1.id]  # terbaru dulu
    assert r.json()["items"][0]["kode_serap"] == ["SUMBER_KOSONG"]
    p = c.get(URL, params={"sasaran_id": sid, "limit": 1, "offset": 1}).json()
    assert p["total"] == 3 and [i["id"] for i in p["items"]] == [u2.id]
    assert u3.id not in [i["id"] for i in r.json()["items"]]
    assert c.get(URL, params={"hasil_serap": "NGAWUR"}).status_code == 422


def test_search_domain_sah_dan_belum_diserap(client_as, db_session):
    sid = str(uuid.uuid4())
    sudah = _usulan(db_session, sasaran_id=sid, menit=1)
    belum = _usulan(db_session, sasaran_id=sid, menit=2, hasil_serap=None)
    c = _tim(client_as)
    r = c.post(
        f"{URL}/search",
        json={"domain": [["sasaran_id", "=", sid], ["hasil_serap", "=", None]]},
    )
    assert r.status_code == 200, r.text
    assert [i["id"] for i in r.json()["items"]] == [belum.id]
    r2 = c.post(
        f"{URL}/search",
        json={
            "domain": [["sasaran_id", "=", sid]],
            "order": [["created_at", "asc"]],
            "limit": 1,
        },
    )
    assert r2.json()["total"] == 2
    assert [i["id"] for i in r2.json()["items"]] == [sudah.id]
    for i in r.json()["items"] + r2.json()["items"]:
        assert set(i) == KUNCI_RINGKAS
    _tanpa_identitas(r.text, belum)
    _tanpa_identitas(r2.text, sudah)
    assert PENANDA_ISI not in r2.text and PENANDA_AMPLOP not in r2.text


@pytest.mark.parametrize(
    "body",
    [
        {"domain": [["isi", "ilike", "x"]]},
        {"domain": [["amplop", "ilike", "x"]]},
        {"domain": [["output_hash", "=", "x"]]},
        {"domain": [["ai_run_id", "=", "x"]]},
        {"domain": [["diminta_oleh", "=", "tim-1"]]},
        {"domain": [["sumber_ids", "=", ["s1"]]]},
        {"domain": [["fungsi", "=", "P09"]], "order": [["diminta_oleh", "asc"]]},
        {"domain": [["diserap_at", "=", None]]},
        {"domain": [["fungsi", "=", "P09"]], "order": [["isi", "asc"]]},
        {"domain": [["isi", "like", "RAHASIA"]]},
    ],
)
def test_search_di_luar_whitelist_422(client_as, db_session, body):
    _usulan(db_session)
    r = _tim(client_as).post(f"{URL}/search", json=body)
    assert r.status_code == 422, r.text
    assert PENANDA_ISI not in r.text and PENANDA_AMPLOP not in r.text


def test_otorisasi_tiga_rute(anon_client, client_as, db_session):
    rec = _usulan(db_session)
    rute = [
        ("GET", URL, None),
        ("GET", f"{URL}/{rec.id}", None),
        ("POST", f"{URL}/search", {}),
        ("POST", f"{URL}/search", {"domain": "salah", "limit": -5}),  # body salah
    ]
    for metode, url, body in rute:
        r = anon_client.request(metode, url, json=body)
        assert r.status_code == 401, (metode, url, r.status_code)
    for grup in (["admin"], ["sekolah-pengisi"], ["admin", "sekolah-pengisi"], []):
        c = client_as("bukan-tim", groups=grup)
        for metode, url, body in rute:
            r = c.request(metode, url, json=body)
            assert r.status_code == 403, (grup, metode, url, r.status_code)
            assert PENANDA_ISI not in r.text


def test_isi_dan_amplop_tidak_masuk_log_maupun_galat(client_as, db_session, caplog):
    rec = _usulan(db_session)
    c = _tim(client_as)
    with caplog.at_level(logging.DEBUG):
        c.get(f"{URL}/{rec.id}")
        c.get(URL)
        c.post(f"{URL}/search", json={"domain": [["fungsi", "=", "P09"]]})
        galat = [
            c.post(f"{URL}/search", json={"domain": [["isi", "ilike", "x"]]}),
            c.post(f"{URL}/search", json={"domain": [["amplop", "=", "x"]]}),
            c.get(f"{URL}/{uuid.uuid4()}"),
        ]
    assert [g.status_code for g in galat] == [422, 422, 404]
    for g in galat:
        assert PENANDA_ISI not in g.text and PENANDA_AMPLOP not in g.text
    for penanda in (PENANDA_ISI, PENANDA_AMPLOP, PENANDA_MASUKAN, PENANDA_KELUARAN):
        assert penanda not in caplog.text


def test_skema_ringkas_tanpa_keluaran_model_dan_run_tetap_tertutup():
    assert set(AiUsulanRingkas.model_fields) == KUNCI_RINGKAS
    assert set(AiUsulanRead.model_fields) == KUNCI_DETAIL
    assert not ({"masukan", "keluaran"} & set(AiUsulanRead.model_fields))
    assert not ({"masukan", "keluaran"} & set(AiRunRead.model_fields))


def test_openapi_rute_usulan_tanpa_ubah_hapus_dan_skema_tertutup(client):
    spec = client.get("/openapi.json").json()
    paths = spec["paths"]
    ops = {(m.upper(), p) for p, v in paths.items() if p.startswith(URL) for m in v}
    assert ops == {
        ("GET", URL),
        ("GET", f"{URL}/{{usulan_id}}"),
        ("POST", f"{URL}/search"),
        ("POST", f"{URL}/{{usulan_id}}/putusan"),
    }
    for p, v in paths.items():
        if p.startswith(URL):
            for op in v.values():
                assert op["summary"] and op["tags"] == ["ai"]
                assert {"401", "403", "429"} <= set(op["responses"])
    skema = spec["components"]["schemas"]
    assert not ({"masukan", "keluaran"} & set(skema["AiUsulanRead"]["properties"]))
    assert not ({"masukan", "keluaran"} & set(skema["AiRunRead"]["properties"]))
    assert set(skema["AiUsulanRingkas"]["properties"]) == KUNCI_RINGKAS
    assert set(skema["AiUsulanRead"]["properties"]) == KUNCI_DETAIL
    for nama in ("ai_run_id", "sumber_ids", "diminta_oleh"):
        assert nama in skema["AiUsulanRead"]["required"]
        assert nama not in skema["AiUsulanRingkas"]["properties"]
