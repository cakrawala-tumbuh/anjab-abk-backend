"""Tes putusan reviewer atas usulan AI (`POST /api/v1/ai/usulan/{id}/putusan`).

Data sintetis; tidak ada panggilan model. Baris `ai_usulan` dibuat langsung. Penanda pada
`catatan` dan `teks_koreksi` dilacak agar tidak muncul di daftar, galat 422, maupun log.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from anjab_abk_backend.models import (
    AiRunModel,
    AiUsulanModel,
    AiUsulanPutusanModel,
    NarasiEventModel,
    NarasiKasusModel,
    NarasiVersiModel,
    NarasiVersiSumberModel,
)
from anjab_abk_backend.services import ai_usulan_sql

URL = "/api/v1/ai/usulan"
PENANDA_CATATAN = "CATATAN-RAHASIA-SINTETIS-5521"
PENANDA_KOREKSI = "KOREKSI-RAHASIA-SINTETIS-8837"
_DASAR = datetime(2026, 11, 1, tzinfo=UTC)


def _tim(client_as, subject: str = "tim-1"):
    return client_as(subject, groups=["tim-kajian"])


def _usulan(db: Session, *, hasil_serap: str | None = "USULAN_DIBUAT", menit: int = 0):
    run_id = str(uuid.uuid4())
    db.add(
        AiRunModel(
            id=run_id,
            fungsi="P09",
            prompt_version="v1",
            prompt_hash="a" * 64,
            model_diminta="model-uji",
            protocol_id="uji",
            input_snapshot_id="b" * 64,
            sumber=[],
            masukan={},
            keluaran={},
            status_qa="LOLOS",
            kode_qa=[],
        )
    )
    db.flush()
    diserap = hasil_serap is not None
    rec = AiUsulanModel(
        id=str(uuid.uuid4()),
        fungsi="P09",
        sasaran_jenis="NARASI_KASUS",
        sasaran_id=str(uuid.uuid4()),
        job_id=str(uuid.uuid4()),
        ai_run_id=run_id,
        sumber_ids=["s1"],
        diminta_oleh="tim-1",
        created_at=_DASAR + timedelta(minutes=menit),
        diserap_at=_DASAR if diserap else None,
        hasil_serap=hasil_serap,
        isi={"ringkasan": "x"} if diserap else None,
        amplop={"catatan": "y"} if diserap else None,
        output_hash="c" * 64 if diserap else None,
    )
    db.add(rec)
    db.flush()
    return rec


def _hitung(db: Session, model: Any) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


def _revise(**kw: Any) -> dict[str, Any]:
    return {"putusan": "REVISE", "tingkat_koreksi": "MINOR", "teks_koreksi": "Teks baru.", **kw}


# --- positif -------------------------------------------------------------------------------


def test_tiga_putusan_tersimpan_dengan_aktor_dari_token(client_as, db_session):
    rec = _usulan(db_session)
    c = _tim(client_as, "reviewer-9")
    badan = [
        {"putusan": "APPROVE"},
        {"putusan": "APPROVE", "catatan": "Sudah sesuai sumber."},
        _revise(catatan=PENANDA_CATATAN, teks_koreksi=PENANDA_KOREKSI),
        {"putusan": "REJECT", "tingkat_koreksi": "CRITICAL", "catatan": "Tidak berdasar."},
    ]
    for b in badan:
        r = c.post(f"{URL}/{rec.id}/putusan", json=b)
        assert r.status_code == 201, r.text
        d = r.json()
        assert d["actor_key"] == "reviewer-9"
        assert d["usulan_id"] == rec.id
        assert d["putusan"] == b["putusan"]
    assert _hitung(db_session, AiUsulanPutusanModel) == 4


def test_aktor_pada_body_diabaikan(client_as, db_session):
    rec = _usulan(db_session)
    r = _tim(client_as, "reviewer-1").post(
        f"{URL}/{rec.id}/putusan",
        json={"putusan": "APPROVE", "actor_key": "penyamar", "aktor": "penyamar", "reviewer": "x"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["actor_key"] == "reviewer-1"
    baris = db_session.scalars(select(AiUsulanPutusanModel)).one()
    assert baris.actor_key == "reviewer-1"


def test_evidence_gap_boleh_diputus(client_as, db_session):
    rec = _usulan(db_session, hasil_serap="EVIDENCE_GAP")
    assert (
        _tim(client_as).post(f"{URL}/{rec.id}/putusan", json={"putusan": "APPROVE"}).status_code
        == 201
    )


# --- validasi ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "badan",
    [
        {"putusan": "REVISE", "tingkat_koreksi": "MINOR"},
        {"putusan": "REVISE", "tingkat_koreksi": "MINOR", "teks_koreksi": "   \n "},
        {"putusan": "REVISE", "teks_koreksi": "Teks baru."},
        {"putusan": "REJECT", "tingkat_koreksi": "MAJOR"},
        {"putusan": "REJECT", "tingkat_koreksi": "MAJOR", "catatan": "      "},
        {"putusan": "REJECT", "tingkat_koreksi": "MAJOR", "catatan": "  abc  "},
        {"putusan": "REJECT", "tingkat_koreksi": "MAJOR", "catatan": "1234"},
        {"putusan": "REJECT", "catatan": "Alasan cukup panjang."},
        {
            "putusan": "REJECT",
            "tingkat_koreksi": "MAJOR",
            "catatan": "Alasan cukup.",
            "teks_koreksi": "x",
        },
        {"putusan": "APPROVE", "tingkat_koreksi": "MINOR"},
        {"putusan": "APPROVE", "teks_koreksi": "x"},
        {"putusan": "TOLAK"},
        {"putusan": "approve"},
        {},
        {"putusan": "REVISE", "tingkat_koreksi": "FATAL", "teks_koreksi": "x"},
        {"putusan": "REVISE", "tingkat_koreksi": "MINOR", "teks_koreksi": "x" * 20001},
    ],
)
def test_kombinasi_tidak_sah_422_tanpa_baris(client_as, db_session, badan):
    rec = _usulan(db_session)
    r = _tim(client_as).post(f"{URL}/{rec.id}/putusan", json=badan)
    assert r.status_code == 422, r.text
    assert _hitung(db_session, AiUsulanPutusanModel) == 0


def test_422_dan_log_tidak_menggemakan_teks_bebas(client_as, db_session, caplog):
    rec = _usulan(db_session)
    badan = {
        "putusan": "REJECT",
        "tingkat_koreksi": "NGAWUR",
        "catatan": PENANDA_CATATAN,
        "teks_koreksi": PENANDA_KOREKSI,
    }
    with caplog.at_level(logging.DEBUG):
        r1 = _tim(client_as).post(f"{URL}/{rec.id}/putusan", json=badan)
        r2 = _tim(client_as).post(  # REJECT dengan teks_koreksi -> 422 dari validator model
            f"{URL}/{rec.id}/putusan",
            json={**badan, "tingkat_koreksi": "MAJOR"},
        )
        r3 = _tim(client_as).post(  # lolos: catatan masuk DB, tetap tak boleh masuk log
            f"{URL}/{rec.id}/putusan",
            json={"putusan": "REJECT", "tingkat_koreksi": "MAJOR", "catatan": PENANDA_CATATAN},
        )
    assert r1.status_code == 422 and r2.status_code == 422 and r3.status_code == 201
    for teks in (r1.text, r2.text):
        assert PENANDA_CATATAN not in teks and PENANDA_KOREKSI not in teks
    assert PENANDA_CATATAN not in caplog.text and PENANDA_KOREKSI not in caplog.text


# --- 404 / 409 -----------------------------------------------------------------------------


def test_id_tak_dikenal_404(client_as):
    r = _tim(client_as).post(f"{URL}/{uuid.uuid4()}/putusan", json={"putusan": "APPROVE"})
    assert r.status_code == 404


@pytest.mark.parametrize("hasil", [None, "MANUAL"])
def test_belum_diserap_atau_manual_409(client_as, db_session, hasil):
    rec = _usulan(db_session, hasil_serap=hasil)
    r = _tim(client_as).post(f"{URL}/{rec.id}/putusan", json={"putusan": "APPROVE"})
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "usulan_belum_bisa_diputus"
    assert _hitung(db_session, AiUsulanPutusanModel) == 0


def test_nilai_sah_sama_dengan_enum_kode():
    from anjab_abk_backend.schemas.ai_usulan import HasilSerapUsulan

    assert ai_usulan_sql._BISA_DIPUTUS == {"USULAN_DIBUAT", "EVIDENCE_GAP"}
    assert {h.value for h in HasilSerapUsulan} - ai_usulan_sql._BISA_DIPUTUS == {"MANUAL"}


# --- otorisasi -----------------------------------------------------------------------------


def test_otorisasi_dan_403_mendahului_422_dan_404(anon_client, client_as, db_session):
    rec = _usulan(db_session)
    assert (
        anon_client.post(f"{URL}/{rec.id}/putusan", json={"putusan": "APPROVE"}).status_code == 401
    )
    for grup in (["admin"], ["sekolah-pengisi"], ["admin", "sekolah-pengisi"], []):
        c = client_as("x", groups=grup)
        assert c.post(f"{URL}/{rec.id}/putusan", json={"putusan": "APPROVE"}).status_code == 403
        assert c.post(f"{URL}/{rec.id}/putusan", json={"putusan": "REJECT"}).status_code == 403
        assert (
            c.post(f"{URL}/{uuid.uuid4()}/putusan", json={"putusan": "APPROVE"}).status_code == 403
        )
    assert _hitung(db_session, AiUsulanPutusanModel) == 0


# --- idempotensi ---------------------------------------------------------------------------


def test_idempotency_key_sama_tidak_menggandakan_dan_membalas_tersimpan(client_as, db_session):
    rec = _usulan(db_session)
    c = _tim(client_as)
    h = {"Idempotency-Key": "kunci-putusan-1"}
    r1 = c.post(f"{URL}/{rec.id}/putusan", json={"putusan": "APPROVE"}, headers=h)
    r2 = c.post(f"{URL}/{rec.id}/putusan", json={"putusan": "APPROVE"}, headers=h)
    assert r1.status_code == 201 and r2.status_code == 200, r2.text
    assert r1.json() == r2.json()
    assert _hitung(db_session, AiUsulanPutusanModel) == 1


def test_key_berbeda_tetap_dua_baris(client_as, db_session):
    rec = _usulan(db_session)
    c = _tim(client_as)
    for k in ("k-a", "k-b"):
        r = c.post(
            f"{URL}/{rec.id}/putusan", json={"putusan": "APPROVE"}, headers={"Idempotency-Key": k}
        )
        assert r.status_code == 201
    assert _hitung(db_session, AiUsulanPutusanModel) == 2


def test_galat_404_dan_409_tidak_mengunci_key_dan_tidak_menjadi_respons_tersimpan(
    client_as, db_session
):
    c = _tim(client_as)
    h = {"Idempotency-Key": "kunci-galat"}
    belum = _usulan(db_session, hasil_serap=None)
    url = f"{URL}/{belum.id}/putusan"
    assert c.post(url, json={"putusan": "APPROVE"}, headers=h).status_code == 409
    assert (
        c.post(url, json={"putusan": "APPROVE"}, headers=h).status_code == 409
    )  # bukan 'sedang diproses'
    belum.diserap_at, belum.hasil_serap = _DASAR, "USULAN_DIBUAT"
    db_session.flush()
    r = c.post(url, json={"putusan": "APPROVE"}, headers=h)
    assert r.status_code == 201, r.text  # key yang pernah gagal masih bisa dipakai
    h404 = {"Idempotency-Key": "kunci-404"}
    u404 = f"{URL}/{uuid.uuid4()}/putusan"
    assert c.post(u404, json={"putusan": "APPROVE"}, headers=h404).status_code == 404
    assert c.post(u404, json={"putusan": "APPROVE"}, headers=h404).status_code == 404


# --- urutan "terbaru" ----------------------------------------------------------------------


def test_putusan_terakhir_deterministik_walau_jam_bernilai_sama(client_as, db_session, monkeypatch):
    """Jam dibekukan (seperti `now()` dalam satu transaksi): stempel harus tetap naik ketat."""
    beku = datetime(2026, 11, 2, 10, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(ai_usulan_sql, "_sekarang", lambda: beku)
    rec = _usulan(db_session)
    c = _tim(client_as)
    urutan = ["APPROVE", "REVISE", "APPROVE", "REJECT"]
    for p in urutan:
        b = {"putusan": p}
        if p == "REVISE":
            b = _revise()
        if p == "REJECT":
            b = {"putusan": "REJECT", "tingkat_koreksi": "MAJOR", "catatan": "Alasan cukup."}
        assert c.post(f"{URL}/{rec.id}/putusan", json=b).status_code == 201
    stempel = [
        r.created_at
        for r in db_session.scalars(
            select(AiUsulanPutusanModel).order_by(AiUsulanPutusanModel.created_at)
        )
    ]
    assert len(set(stempel)) == len(stempel), "created_at tidak boleh kembar per usulan"
    d = c.get(f"{URL}/{rec.id}").json()
    assert [p["putusan"] for p in d["putusan"]] == urutan
    assert d["putusan_terakhir"]["putusan"] == "REJECT"
    assert d["putusan_terakhir"]["id"] == d["putusan"][-1]["id"]
    daftar = c.get(URL).json()["items"][0]
    assert daftar["putusan_terakhir"]["id"] == d["putusan"][-1]["id"]


# --- daftar, pencarian, kebocoran, N+1 -----------------------------------------------------


def test_list_dan_search_memuat_putusan_terakhir_tanpa_teks_bebas(client_as, db_session):
    a = _usulan(db_session, menit=1)
    b = _usulan(db_session, menit=2)
    _usulan(db_session, menit=3)
    c = _tim(client_as, "r-1")
    c.post(f"{URL}/{a.id}/putusan", json={"putusan": "APPROVE", "catatan": PENANDA_CATATAN})
    c.post(f"{URL}/{a.id}/putusan", json=_revise(teks_koreksi=PENANDA_KOREKSI))
    c.post(
        f"{URL}/{b.id}/putusan",
        json={"putusan": "REJECT", "tingkat_koreksi": "CRITICAL", "catatan": PENANDA_CATATAN},
    )
    for r in (c.get(URL), c.post(f"{URL}/search", json={"domain": [], "limit": 10})):
        assert r.status_code == 200, r.text
        assert PENANDA_CATATAN not in r.text and PENANDA_KOREKSI not in r.text
        items = {i["id"]: i for i in r.json()["items"]}
        assert items[a.id]["putusan_terakhir"]["putusan"] == "REVISE"
        assert items[a.id]["putusan_terakhir"]["tingkat_koreksi"] == "MINOR"
        assert items[b.id]["putusan_terakhir"]["putusan"] == "REJECT"
        assert items[b.id]["putusan_terakhir"]["actor_key"] == "r-1"
        sisa = [i for i in items.values() if i["id"] not in (a.id, b.id)]
        assert sisa and all(i["putusan_terakhir"] is None for i in sisa)
        for i in items.values():
            assert not ({"isi", "amplop", "output_hash", "putusan"} & set(i))
            if i["putusan_terakhir"]:
                assert not ({"catatan", "teks_koreksi"} & set(i["putusan_terakhir"]))


def _hitung_kueri(db: Session, panggil) -> int:
    kalimat: list[str] = []

    def _tangkap(conn, cursor, statement, *_a):
        kalimat.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", _tangkap)
    try:
        panggil()
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", _tangkap)
    return len(kalimat)


def test_putusan_terakhir_tanpa_n_plus_1_pada_list_dan_search(client_as, db_session):
    c = _tim(client_as)

    def _sisip(n: int) -> None:
        for i in range(n):
            u = _usulan(db_session, menit=100 + i)
            for _ in range(2):
                assert (
                    c.post(f"{URL}/{u.id}/putusan", json={"putusan": "APPROVE"}).status_code == 201
                )

    _sisip(1)
    k1 = (
        _hitung_kueri(db_session, lambda: c.get(URL, params={"limit": 50})),
        _hitung_kueri(
            db_session, lambda: c.post(f"{URL}/search", json={"domain": [], "limit": 50})
        ),
    )
    _sisip(7)
    k8 = (
        _hitung_kueri(db_session, lambda: c.get(URL, params={"limit": 50})),
        _hitung_kueri(
            db_session, lambda: c.post(f"{URL}/search", json={"domain": [], "limit": 50})
        ),
    )
    assert k1 == k8, (k1, k8)
    assert len(c.get(URL, params={"limit": 50}).json()["items"]) == 8


def test_detail_memuat_putusan_lengkap_urut_naik(client_as, db_session):
    rec = _usulan(db_session)
    c = _tim(client_as)
    c.post(
        f"{URL}/{rec.id}/putusan",
        json=_revise(catatan=PENANDA_CATATAN, teks_koreksi=PENANDA_KOREKSI),
    )
    d = c.get(f"{URL}/{rec.id}").json()
    assert d["putusan"][0]["catatan"] == PENANDA_CATATAN
    assert d["putusan"][0]["teks_koreksi"] == PENANDA_KOREKSI


# --- tulisan terbatas ----------------------------------------------------------------------


def _tabel_tertulis(db: Session, panggil) -> set[str]:
    ditulis: list[str] = []

    def _catat(session: Session, _ctx: Any, _inst: Any) -> None:
        ditulis.extend(type(o).__name__ for o in (*session.new, *session.dirty, *session.deleted))

    event.listen(db, "before_flush", _catat)
    try:
        panggil()
        db.flush()
    finally:
        event.remove(db, "before_flush", _catat)
    return set(ditulis)


def test_hanya_ai_usulan_putusan_yang_tertulis_tanpa_tabel_narasi(client_as, db_session):
    rec = _usulan(db_session)
    c = _tim(client_as)
    tanpa_key = _tabel_tertulis(
        db_session, lambda: c.post(f"{URL}/{rec.id}/putusan", json={"putusan": "APPROVE"})
    )
    assert tanpa_key == {"AiUsulanPutusanModel"}
    dengan_key = _tabel_tertulis(
        db_session,
        lambda: c.post(
            f"{URL}/{rec.id}/putusan",
            json={"putusan": "APPROVE"},
            headers={"Idempotency-Key": "k-tulis"},
        ),
    )
    assert dengan_key == {"AiUsulanPutusanModel", "IdempotencyRecord"}
    for model in (NarasiEventModel, NarasiVersiModel, NarasiVersiSumberModel, NarasiKasusModel):
        assert _hitung(db_session, model) == 0
    row = db_session.get(AiUsulanModel, rec.id)
    assert (row.hasil_serap, row.diserap_at) == ("USULAN_DIBUAT", _DASAR)


# --- OpenAPI -------------------------------------------------------------------------------


def test_openapi_putusan_hanya_post_dan_skema_lama_hanya_bertambah(client):
    spec = client.get("/openapi.json").json()
    path = f"{URL}/{{usulan_id}}/putusan"
    assert set(spec["paths"][path]) == {"post"}
    op = spec["paths"][path]["post"]
    assert {"201", "401", "403", "404", "409", "422", "429"} <= set(op["responses"])
    assert not [p for p in spec["paths"] if p.startswith(URL) and p.endswith("putusan/{x}")]
    skema = spec["components"]["schemas"]
    assert "putusan_terakhir" in skema["AiUsulanRingkas"]["properties"]
    assert "putusan" in skema["AiUsulanRead"]["properties"]
    assert "actor_key" not in skema["AiUsulanPutusanCreate"]["properties"]
    assert set(skema["AiUsulanPutusanCreate"]["properties"]) == {
        "putusan",
        "tingkat_koreksi",
        "catatan",
        "teks_koreksi",
    }
    assert not ({"catatan", "teks_koreksi"} & set(skema["AiUsulanPutusanTerakhir"]["properties"]))
