"""Tes penerapan usulan P04 menjadi register klarifikasi (`POST .../dari-usulan/{id}`, #137).

Data sintetis; baris `ai_run`, `ai_usulan`, dan `ai_usulan_putusan` dibuat langsung di DB.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from anjab_abk_backend.models import (
    AiRunModel,
    AiUsulanModel,
    AiUsulanPutusanModel,
    NarasiKlarifikasiModel,
)

URL = "/api/v1/narasi/klarifikasi"
DARI = f"{URL}/dari-usulan"
KASUS = "/api/v1/narasi/kasus"
_DASAR = datetime(2026, 11, 1, tzinfo=UTC)


def _isi(**ubah: Any) -> dict[str, Any]:
    isi: dict[str, Any] = {
        "material": True,
        "materiality_rationale": "Menentukan beban kerja guru.",
        "one_neutral_question": "Berapa jam per minggu tugas ini dikerjakan?",
        "why_ask": "Menetapkan norma waktu.",
        "preferred_role": "kepala-sekolah",
        "alternatives": ["Periksa log harian", "Periksa jadwal mengajar"],
        "limitations": [],
    }
    isi.update(ubah)
    return isi


def _tim(client_as, subject: str):
    return client_as(subject, groups=["tim-kajian"])


def _kasus(client_as) -> str:
    r = _tim(client_as, "penyusun-kasus").post(
        KASUS,
        json={
            "instrument_id": "wcp",
            "field_key": f"f-{uuid.uuid4().hex[:8]}",
            "peran_ref": "guru",
            "periode": "2026/27",
            "narrative_kind": "F1_FORMAL",
            "intended_use": "uji",
            "permission_scope": "internal",
            "sensitivity_class": "NONPRIBADI",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _usulan(
    db: Session,
    sasaran_id: str,
    *,
    fungsi: str = "P04",
    sasaran_jenis: str = "NARASI_KASUS",
    isi: dict[str, Any] | None = None,
    putusan: list[str] | None = ("APPROVE",),  # type: ignore[assignment]
    masukan: dict[str, Any] | None = None,
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
            masukan=masukan,
            keluaran={},
            status_qa="LOLOS",
            kode_qa=[],
        )
    )
    db.flush()
    rec = AiUsulanModel(
        id=str(uuid.uuid4()),
        fungsi=fungsi,
        sasaran_jenis=sasaran_jenis,
        sasaran_id=sasaran_id,
        job_id=str(uuid.uuid4()),
        ai_run_id=run_id,
        sumber_ids=["src-1", "klaim:abc"],
        diminta_oleh="tim-1",
        created_at=_DASAR,
        diserap_at=_DASAR,
        hasil_serap="USULAN_DIBUAT",
        isi=_isi() if isi is None else isi,
        amplop={"source_refs": ["src-1"]},
        output_hash="c" * 64,
    )
    db.add(rec)
    db.flush()
    for i, p in enumerate(putusan or []):
        db.add(
            AiUsulanPutusanModel(
                id=str(uuid.uuid4()),
                usulan_id=rec.id,
                putusan=p,
                tingkat_koreksi=None if p == "APPROVE" else "MINOR",
                catatan="Catatan reviewer." if p == "REJECT" else None,
                teks_koreksi="Koreksi bebas." if p == "REVISE" else None,
                actor_key="reviewer-1",
                created_at=_DASAR + timedelta(minutes=i + 1),
            )
        )
    db.flush()
    return rec


def _body(**ubah: Any) -> dict[str, Any]:
    body = {"claim_id": "C-1", "due_trigger": "Sebelum rapat.", "exposure": "BELUM_TERPAPAR"}
    body.update(ubah)
    return body


def test_approve_memetakan_seluruh_field(client_as, db_session):
    nid = _kasus(client_as)
    u = _usulan(db_session, nid, masukan={"parameter": {"periode": "2026/27"}})
    r = _tim(client_as, "pembuat").post(f"{DARI}/{u.id}", json=_body())
    assert r.status_code == 201, r.text
    d = r.json()
    assert d["question_text"] == "Berapa jam per minggu tugas ini dikerjakan?"
    assert d["materiality_reason"] == "Menentukan beban kerja guru."
    assert d["alternative_hypothesis"] == "- Periksa log harian\n- Periksa jadwal mengajar"
    assert d["recipient_role"] == "kepala-sekolah"
    assert d["intended_decision"] == "Menetapkan norma waktu."
    assert d["source_ids_checked"] == ["src-1", "klaim:abc"]
    assert d["narasi_id"] == nid and d["periode"] == "2026/27" and d["ai_usulan_id"] == u.id
    assert d["claim_id"] == "C-1" and d["exposure"] == "BELUM_TERPAPAR"
    assert d["reviewer_approval"] == "MENUNGGU" and d["disposition"] == "TERBUKA"
    assert d["dibuat_oleh"] == "pembuat"
    assert [(e["aksi"], e["catatan"]) for e in d["riwayat"]] == [
        ("DIBUAT", f"dari usulan P04 {u.id}")
    ]


def test_intended_decision_body_menang_dan_periode_cadangan_dari_kasus(client_as, db_session):
    nid = _kasus(client_as)
    u = _usulan(db_session, nid, putusan=["REVISE"])  # masukan None -> periode dari kasus
    r = _tim(client_as, "pembuat").post(
        f"{DARI}/{u.id}", json=_body(intended_decision="Keputusan dari body.")
    )
    assert r.status_code == 201, r.text
    assert r.json()["intended_decision"] == "Keputusan dari body."
    assert r.json()["periode"] == "2026/27"


def test_alternatives_kosong_memakai_teks_bawaan(client_as, db_session):
    u = _usulan(db_session, _kasus(client_as), isi=_isi(alternatives=[]))
    r = _tim(client_as, "pembuat").post(f"{DARI}/{u.id}", json=_body())
    assert r.status_code == 201, r.text
    assert r.json()["alternative_hypothesis"] == "Tidak ada alternatif yang diusulkan P04."


def test_terapkan_dua_kali_409_dengan_id_klarifikasi(client_as, db_session):
    u = _usulan(db_session, _kasus(client_as))
    c = _tim(client_as, "pembuat")
    kid = c.post(f"{DARI}/{u.id}", json=_body()).json()["id"]
    r = c.post(f"{DARI}/{u.id}", json=_body(claim_id="C-2"))
    assert r.status_code == 409 and r.json()["error"] == "USULAN_SUDAH_DITERAPKAN"
    assert r.json()["details"][0]["msg"] == kid


def test_unique_ai_usulan_dijaga_basis_data(client_as, db_session):
    u = _usulan(db_session, _kasus(client_as))
    _tim(client_as, "pembuat").post(f"{DARI}/{u.id}", json=_body())
    asal = db_session.scalar(
        select(NarasiKlarifikasiModel).where(NarasiKlarifikasiModel.ai_usulan_id == u.id)
    )
    with pytest.raises(IntegrityError, match="uq_narasi_klarifikasi_ai_usulan"):
        with db_session.begin_nested():
            db_session.execute(
                text(
                    "INSERT INTO narasi_klarifikasi (id, narasi_id, claim_id, source_ids_checked,"
                    " materiality_reason, alternative_hypothesis, intended_decision,"
                    " recipient_role, periode, exposure, due_trigger, question_text,"
                    " ai_usulan_id, dibuat_oleh, created_at, updated_at) SELECT :i, narasi_id,"
                    " 'C-9', source_ids_checked, materiality_reason, alternative_hypothesis,"
                    " intended_decision, recipient_role, periode, exposure, due_trigger,"
                    " question_text, ai_usulan_id, dibuat_oleh, now(), now()"
                    " FROM narasi_klarifikasi WHERE id = :a"
                ),
                {"i": str(uuid.uuid4()), "a": asal.id},
            )


def test_usulan_fungsi_lain_422(client_as, db_session):
    nid = _kasus(client_as)
    c = _tim(client_as, "pembuat")
    u = _usulan(db_session, nid, fungsi="P11", sasaran_jenis="REDESAIN_KONTEKS")
    r = c.post(f"{DARI}/{u.id}", json=_body())
    assert r.status_code == 422 and r.json()["error"] == "USULAN_BUKAN_P04"
    u2 = _usulan(db_session, nid, sasaran_jenis="JABATAN")
    assert c.post(f"{DARI}/{u2.id}", json=_body()).json()["error"] == "USULAN_BUKAN_P04"


@pytest.mark.parametrize("putusan", [[], ["REJECT"], ["APPROVE", "REJECT"]])
def test_belum_diterima_409(client_as, db_session, putusan):
    u = _usulan(db_session, _kasus(client_as), putusan=putusan)
    r = _tim(client_as, "pembuat").post(f"{DARI}/{u.id}", json=_body())
    assert r.status_code == 409 and r.json()["error"] == "USULAN_BELUM_DITERIMA"


def test_putusan_terakhir_approve_setelah_reject_diterima(client_as, db_session):
    u = _usulan(db_session, _kasus(client_as), putusan=["REJECT", "APPROVE"])
    r = _tim(client_as, "pembuat").post(f"{DARI}/{u.id}", json=_body())
    assert r.status_code == 201, r.text


@pytest.mark.parametrize(
    "isi",
    [
        _isi(material=False),
        _isi(one_neutral_question=None),
        _isi(one_neutral_question="   "),
    ],
)
def test_tidak_material_422(client_as, db_session, isi):
    u = _usulan(db_session, _kasus(client_as), isi=isi)
    r = _tim(client_as, "pembuat").post(f"{DARI}/{u.id}", json=_body())
    assert r.status_code == 422 and r.json()["error"] == "USULAN_TIDAK_MATERIAL"


def test_periode_tak_ada_422(client_as, db_session):
    u = _usulan(db_session, str(uuid.uuid4()))  # kasus tak ada, masukan None
    r = _tim(client_as, "pembuat").post(f"{DARI}/{u.id}", json=_body())
    assert r.status_code == 422 and r.json()["error"] == "PERIODE_TAK_ADA"


def test_kasus_tak_ada_dengan_periode_parameter_404(client_as, db_session):
    u = _usulan(db_session, str(uuid.uuid4()), masukan={"parameter": {"periode": "2026/27"}})
    assert _tim(client_as, "pembuat").post(f"{DARI}/{u.id}", json=_body()).status_code == 404


def test_isian_usulan_kurang_422(client_as, db_session):
    nid = _kasus(client_as)
    c = _tim(client_as, "pembuat")
    u = _usulan(db_session, nid, isi=_isi(why_ask=None))
    r = c.post(f"{DARI}/{u.id}", json=_body())
    assert r.status_code == 422 and r.json()["error"] == "ISIAN_USULAN_KURANG"
    assert c.post(f"{DARI}/{u.id}", json=_body(intended_decision="Dari body.")).status_code == 201
    u2 = _usulan(db_session, nid, isi=_isi(preferred_role=None))
    r = c.post(f"{DARI}/{u2.id}", json=_body(claim_id="C-7"))
    assert r.status_code == 422 and r.json()["error"] == "ISIAN_USULAN_KURANG"


def test_usulan_acak_404_dan_body_tidak_sah_422(client_as, db_session):
    c = _tim(client_as, "pembuat")
    assert c.post(f"{DARI}/{uuid.uuid4()}", json=_body()).status_code == 404
    u = _usulan(db_session, _kasus(client_as))
    assert c.post(f"{DARI}/{u.id}", json={"claim_id": "C-1"}).status_code == 422
    assert c.post(f"{DARI}/{u.id}", json=_body(exposure="ASING")).status_code == 422
    assert c.post(f"{DARI}/{u.id}", json={**_body(), "ekstra": 1}).status_code == 422


def test_klaim_sudah_terbuka_409_ganda_dan_usulan_tetap_bebas(client_as, db_session):
    nid = _kasus(client_as)
    c = _tim(client_as, "pembuat")
    body = {
        "narasi_id": nid,
        "claim_id": "C-1",
        "source_ids_checked": ["s"],
        "materiality_reason": "m",
        "alternative_hypothesis": "a",
        "intended_decision": "i",
        "recipient_role": "r",
        "periode": "2026/27",
        "exposure": "BELUM_TERPAPAR",
        "due_trigger": "t",
        "question_text": "Apa?",
    }
    assert c.post(URL, json=body).status_code == 201
    u = _usulan(db_session, nid)
    r = c.post(f"{DARI}/{u.id}", json=_body())
    assert r.status_code == 409 and r.json()["error"] == "KLARIFIKASI_GANDA"
    assert (
        _tim(client_as, "pembuat").post(f"{DARI}/{u.id}", json=_body(claim_id="C-2")).status_code
        == 201
    )


def test_tolak_baris_dari_usulan_lalu_klaim_sama_boleh_diberi_klarifikasi_baru(
    client_as, db_session
):
    nid = _kasus(client_as)
    u = _usulan(db_session, nid)
    c = _tim(client_as, "pembuat")
    kid = c.post(f"{DARI}/{u.id}", json=_body()).json()["id"]
    r = _tim(client_as, "reviewer").post(
        f"{URL}/{kid}/persetujuan", json={"keputusan": "TOLAK", "catatan": "kurang netral"}
    )
    assert r.status_code == 200 and r.json()["disposition"] == "DITOLAK"
    u2 = _usulan(db_session, nid)
    assert c.post(f"{DARI}/{u2.id}", json=_body()).status_code == 201
    # usulan yang barisnya ditolak tetap tak bisa diterapkan ulang (tepat sekali)
    r = c.post(f"{DARI}/{u.id}", json=_body(claim_id="C-3"))
    assert r.status_code == 409 and r.json()["error"] == "USULAN_SUDAH_DITERAPKAN"


def test_bukan_tim_kajian_403(client_as, db_session):
    u = _usulan(db_session, _kasus(client_as))
    luar = client_as("orang-luar", groups=["partisipan"])
    assert luar.post(f"{DARI}/{u.id}", json=_body()).status_code == 403
