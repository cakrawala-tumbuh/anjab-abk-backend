"""Tes skema kasus narasi: UNIQUE lingkup, append-only versi/sumber, enum, tanpa `context_id`."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError, IntegrityError

from anjab_abk_backend.models import (
    AiRunModel,
    NarasiKasusModel,
    NarasiSumberModel,
    NarasiVersiModel,
    NarasiVersiSumberModel,
)
from anjab_abk_backend.narasi.schemas.kasus import (
    BasisRelation,
    NarrativeKind,
    RevisionOrigin,
    StatusNarasi,
)


def _id() -> str:
    return str(uuid.uuid4())


def _kasus(**ubah) -> NarasiKasusModel:
    nilai = {
        "id": _id(),
        "instrument_id": "wcp",
        "field_key": "catatan",
        "peran_ref": "guru",
        "periode": "2026/27",
        "sekolah_id": None,
        "narrative_kind": "F1_FORMAL",
        "status": "SOURCE_CHECKED",
        "intended_use": "uji",
        "permission_scope": "tim",
        "sensitivity_class": "internal",
        "dibuat_oleh": "tester",
    }
    nilai.update(ubah)
    return NarasiKasusModel(**nilai)


def _versi(narasi_id: str, **ubah) -> NarasiVersiModel:
    nilai = {
        "id": _id(),
        "narasi_id": narasi_id,
        "revision_no": 1,
        "revision_origin": "AI_DRAFT",
        "status_hasil": "OK",
        "teks": "isi",
        "dibuat_oleh": "tester",
    }
    nilai.update(ubah)
    return NarasiVersiModel(**nilai)


def _ai_run(run_id: str) -> AiRunModel:
    return AiRunModel(
        id=run_id,
        fungsi="p10",
        prompt_version="v1",
        prompt_hash="h" * 64,
        model_diminta="m",
        protocol_id="p",
        input_snapshot_id="s" * 64,
        sumber=[],
        status_qa="OK",
        kode_qa=[],
    )


def _sumber() -> NarasiSumberModel:
    return NarasiSumberModel(
        id=_id(),
        judul="j",
        jenis="SINTETIS",
        versi="v1",
        periode="2026/27",
        teks="t",
        teks_hash="a" * 64,
        dibuat_oleh="tester",
    )


def _tautan(versi_id: str, sumber_id: str) -> NarasiVersiSumberModel:
    return NarasiVersiSumberModel(
        id=_id(),
        narasi_versi_id=versi_id,
        sumber_id=sumber_id,
        source_hash="b" * 64,
        basis_relation="DIRECT",
    )


def test_lingkup_ganda_dengan_kolom_null_ditolak(db_session):
    db_session.add(_kasus())
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_kasus())
        db_session.flush()


def test_lingkup_beda_satu_kolom_diterima(db_session):
    db_session.add(_kasus())
    db_session.add(_kasus(konteks_kode="K1"))
    db_session.flush()


def test_revision_no_nol_dan_ganda_ditolak(db_session):
    k = _kasus()
    db_session.add(k)
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_versi(k.id, revision_no=0))
        db_session.flush()
    db_session.add(_versi(k.id, revision_no=1))
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_versi(k.id, revision_no=1))
        db_session.flush()


def test_ai_run_id_ganda_ditolak(db_session):
    k = _kasus()
    run_id = _id()
    db_session.add_all([k, _ai_run(run_id)])
    db_session.flush()
    db_session.add(_versi(k.id, revision_no=1, ai_run_id=run_id))
    db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_versi(k.id, revision_no=2, ai_run_id=run_id))
        db_session.flush()


def test_enum_di_luar_daftar_ditolak_check(db_session):
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_kasus(status="ACAK"))
        db_session.flush()
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(_kasus(narrative_kind="F1_FORMAL_DOC"))
        db_session.flush()


def test_update_dan_delete_versi_ditolak(db_session):
    k = _kasus()
    v = _versi(k.id)
    db_session.add(k)
    db_session.flush()
    db_session.add(v)
    db_session.flush()
    with pytest.raises(DBAPIError, match="append-only"), db_session.begin_nested():
        db_session.execute(text("UPDATE narasi_versi SET teks = 'ubah' WHERE id = :i"), {"i": v.id})
    with pytest.raises(DBAPIError, match="append-only"), db_session.begin_nested():
        db_session.execute(text("DELETE FROM narasi_versi WHERE id = :i"), {"i": v.id})


def test_update_dan_delete_versi_sumber_ditolak(db_session):
    k, s = _kasus(), _sumber()
    db_session.add_all([k, s])
    db_session.flush()
    v = _versi(k.id)
    db_session.add(v)
    db_session.flush()
    t = _tautan(v.id, s.id)
    db_session.add(t)
    db_session.flush()
    with pytest.raises(DBAPIError, match="append-only"), db_session.begin_nested():
        db_session.execute(
            text("UPDATE narasi_versi_sumber SET source_span = 'x' WHERE id = :i"), {"i": t.id}
        )
    with pytest.raises(DBAPIError, match="append-only"), db_session.begin_nested():
        db_session.execute(text("DELETE FROM narasi_versi_sumber WHERE id = :i"), {"i": t.id})


def test_status_kasus_proyeksi_boleh_berubah(db_session):
    k = _kasus()
    db_session.add(k)
    db_session.flush()
    k.status = "AI_DRAFT"
    db_session.flush()


def test_tidak_ada_kolom_context_id(db_session):
    insp = inspect(db_session.get_bind())
    for tabel in ("narasi_kasus", "narasi_versi", "narasi_versi_sumber"):
        assert "context_id" not in {c["name"] for c in insp.get_columns(tabel)}


def test_nilai_enum_persis():
    assert [m.value for m in StatusNarasi] == [
        "SOURCE_CHECKED",
        "AI_DRAFT",
        "NEED_FACT",
        "TEAM_REVIEW",
        "TEAM_VERIFIED",
        "SUBJECT_REVIEW",
        "SUBJECT_CONFIRMED",
        "SUBJECT_CORRECTION",
        "SUBJECT_REJECTED",
        "SUBJECT_UNCERTAIN",
        "FINAL_TEAM_REVIEW",
        "RELEASED_FACT",
        "RELEASED_LIMITED",
        "RETURN_FOR_CLARIFICATION",
    ]
    assert len(StatusNarasi) == 14
    assert {m.value for m in NarrativeKind} == {
        "F1_FORMAL",
        "F2_ACTUAL",
        "F3_HANDOFF",
        "F4_ANALYTICAL",
        "F5_RESEARCH",
    }
    assert len(RevisionOrigin) == 5
    assert len(BasisRelation) == 4
