"""Tes `SqlNarasiService`: mesin status tahap Tim, versi basi, sumber, dan append-only event."""

from __future__ import annotations

import hashlib
import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from anjab_abk_backend.errors import ConflictError, ForbiddenError, ValidationAppError
from anjab_abk_backend.models import (
    NarasiEventModel,
    NarasiKasusModel,
    NarasiSumberModel,
    NarasiVersiModel,
)
from anjab_abk_backend.narasi.schemas.kasus import EventKind, RevisionOrigin, StatusNarasi
from anjab_abk_backend.narasi.schemas.mesin import (
    AKTOR_AI_WORKER,
    AktorNarasi,
    KutipanSumber,
    NarasiKasusCreate,
)
from anjab_abk_backend.narasi.services.narasi_sql import SqlNarasiService

TIM = AktorNarasi(key="tim-1", role="REVIEWER")
AI = AktorNarasi(key=AKTOR_AI_WORKER, role="SYSTEM")
S = StatusNarasi


@pytest.fixture
def svc(db_session):
    return SqlNarasiService(db_session)


@pytest.fixture
def sumber(db_session):
    teks = "teks sumber"
    rec = NarasiSumberModel(
        id=str(uuid.uuid4()),
        judul="j",
        jenis="SINTETIS",
        versi="v1",
        periode="2026/27",
        teks=teks,
        teks_hash=hashlib.sha256(teks.encode()).hexdigest(),
        dibuat_oleh="t",
    )
    db_session.add(rec)
    db_session.flush()
    return KutipanSumber(sumber_id=rec.id, source_hash=rec.teks_hash, basis_relation="DIRECT")


def _kasus(svc, **ubah):
    nilai = {
        "instrument_id": "wcp",
        "field_key": f"f-{uuid.uuid4().hex[:8]}",
        "peran_ref": "guru",
        "periode": "2026/27",
        "narrative_kind": "F1_FORMAL",
        "intended_use": "uji",
        "permission_scope": "tim",
        "sensitivity_class": "internal",
    }
    nilai.update(ubah)
    return svc.buat_kasus(NarasiKasusCreate(**nilai), TIM)


def _versi(svc, kasus, sumber, *, supersedes=None, status=S.TEAM_REVIEW, teks="isi", **kw):
    return svc.tambah_versi(
        kasus.id,
        revision_origin=kw.pop("origin", RevisionOrigin.REVIEWER_EDIT),
        status_hasil=status,
        teks=teks,
        sumber=[sumber] if teks is not None else [],
        supersedes_id=supersedes,
        aktor=kw.pop("aktor", TIM),
        **kw,
    )


def _status(db_session, kasus_id):
    db_session.expire_all()
    return db_session.get(NarasiKasusModel, kasus_id).status


def _jumlah_event(db_session):
    return db_session.scalar(select(func.count()).select_from(NarasiEventModel))


def test_kasus_baru_berstatus_source_checked(svc):
    assert _kasus(svc).status == S.SOURCE_CHECKED


def test_lingkup_kasus_ganda_conflict(svc):
    _kasus(svc, field_key="sama")
    with pytest.raises(ConflictError):
        _kasus(svc, field_key="sama")


def test_alur_positif_sampai_team_verified(svc, db_session, sumber):
    k = _kasus(svc)
    v = _versi(svc, k, sumber)
    assert v.revision_no == 1
    e = svc.catat_event(k.id, v.id, EventKind.TEAM_APPROVE, TIM, "ok")
    assert (e.dari_status, e.ke_status) == (S.TEAM_REVIEW, S.TEAM_VERIFIED)
    assert _status(db_session, k.id) == S.TEAM_VERIFIED


def test_team_reject_kembali_source_checked_versi_lama_tetap(svc, db_session, sumber):
    k = _kasus(svc)
    v = _versi(svc, k, sumber)
    svc.catat_event(k.id, v.id, EventKind.TEAM_REJECT, TIM, None)
    assert _status(db_session, k.id) == S.SOURCE_CHECKED
    assert db_session.get(NarasiVersiModel, v.id) is not None
    v2 = _versi(svc, k, sumber, supersedes=v.id, status=S.AI_DRAFT, origin=RevisionOrigin.AI_DRAFT)
    assert v2.revision_no == 2


def test_need_source_lalu_versi_baru_team_review(svc, db_session, sumber):
    k = _kasus(svc)
    svc.catat_event(k.id, None, EventKind.NEED_SOURCE, TIM, None)
    assert _status(db_session, k.id) == S.NEED_FACT
    _versi(svc, k, sumber)
    assert _status(db_session, k.id) == S.TEAM_REVIEW


def test_team_verified_kembali_hanya_lewat_versi_baru(svc, db_session, sumber):
    k = _kasus(svc)
    v = _versi(svc, k, sumber)
    svc.catat_event(k.id, v.id, EventKind.TEAM_APPROVE, TIM, None)
    n = _jumlah_event(db_session)
    with pytest.raises(ConflictError):
        svc.catat_event(k.id, v.id, EventKind.TEAM_REVISE, TIM, None)
    assert _jumlah_event(db_session) == n
    _versi(svc, k, sumber, supersedes=v.id)
    assert _status(db_session, k.id) == S.TEAM_REVIEW


@pytest.mark.parametrize(
    "kind",
    [
        EventKind.SUBJECT_CONFIRM,
        EventKind.SUBJECT_CORRECT,
        EventKind.SUBJECT_REJECT,
        EventKind.SUBJECT_UNSURE,
        EventKind.FINAL_TEAM_APPROVE,
        EventKind.RELEASE_LIMITED,
        EventKind.RETURN_CLARIFICATION,
    ],
)
def test_event_belum_dibuka_conflict(svc, db_session, sumber, kind):
    k = _kasus(svc)
    v = _versi(svc, k, sumber)
    n = _jumlah_event(db_session)
    with pytest.raises(ConflictError) as ei:
        svc.catat_event(k.id, v.id, kind, TIM, None)
    assert ei.value.error_code == "event_belum_dibuka"
    assert _jumlah_event(db_session) == n
    assert _status(db_session, k.id) == S.TEAM_REVIEW


def test_transisi_di_luar_tabel_conflict_tanpa_baris(svc, db_session):
    k = _kasus(svc)  # SOURCE_CHECKED -> TEAM_VERIFIED tidak ada di tabel
    n = _jumlah_event(db_session)
    with pytest.raises(ConflictError) as ei:
        svc.catat_event(k.id, None, EventKind.TEAM_APPROVE, TIM, None)
    assert ei.value.error_code == "transisi_tidak_sah"
    assert _jumlah_event(db_session) == n


def test_aktor_ai_worker_forbidden_tanpa_baris(svc, db_session, sumber):
    k = _kasus(svc)
    v = _versi(svc, k, sumber)
    n = _jumlah_event(db_session)
    with pytest.raises(ForbiddenError):
        svc.catat_event(k.id, v.id, EventKind.TEAM_APPROVE, AI, None)
    assert _jumlah_event(db_session) == n
    assert _status(db_session, k.id) == S.TEAM_REVIEW


def test_ai_worker_boleh_menambah_versi(svc, db_session, sumber):
    k = _kasus(svc)
    v = _versi(svc, k, sumber, status=S.AI_DRAFT, origin=RevisionOrigin.AI_DRAFT, aktor=AI)
    assert v.dibuat_oleh == AKTOR_AI_WORKER
    assert _status(db_session, k.id) == S.AI_DRAFT


def test_supersedes_dan_versi_event_basi(svc, db_session, sumber):
    k = _kasus(svc)
    v1 = _versi(svc, k, sumber)
    with pytest.raises(ConflictError) as ei:
        _versi(svc, k, sumber, supersedes=None)
    assert ei.value.error_code == "versi_basi"
    v2 = _versi(svc, k, sumber, supersedes=v1.id)
    with pytest.raises(ConflictError) as ei:
        _versi(svc, k, sumber, supersedes=v1.id)
    assert ei.value.error_code == "versi_basi"
    n = _jumlah_event(db_session)
    with pytest.raises(ConflictError) as ei:
        svc.catat_event(k.id, v1.id, EventKind.TEAM_APPROVE, TIM, None)
    assert ei.value.error_code == "versi_basi"
    assert _jumlah_event(db_session) == n
    assert v2.revision_no == 2


def test_dua_versi_beruntun_revision_no_urut(svc, sumber):
    k = _kasus(svc)
    v1 = _versi(svc, k, sumber)
    v2 = _versi(svc, k, sumber, supersedes=v1.id)
    assert (v1.revision_no, v2.revision_no) == (1, 2)


def test_versi_berteks_tanpa_sumber_422(svc):
    k = _kasus(svc)
    with pytest.raises(ValidationAppError, match="NO_SOURCE_NO_FACT"):
        svc.tambah_versi(
            k.id,
            revision_origin=RevisionOrigin.REVIEWER_EDIT,
            status_hasil=S.TEAM_REVIEW,
            teks="isi",
            sumber=[],
            supersedes_id=None,
            aktor=TIM,
        )


def test_hash_sumber_tidak_cocok_422(svc, sumber):
    k = _kasus(svc)
    salah = sumber.model_copy(update={"source_hash": "0" * 64})
    with pytest.raises(ValidationAppError, match="NO_SOURCE_NO_FACT"):
        _versi(svc, k, salah)


def test_teks_null_hanya_untuk_need_fact(svc, db_session):
    k = _kasus(svc)
    with pytest.raises(ValidationAppError):
        _versi(svc, k, None, status=S.TEAM_REVIEW, teks=None)
    v = _versi(svc, k, None, status=S.NEED_FACT, teks=None)
    assert v.teks is None
    assert _status(db_session, k.id) == S.NEED_FACT


def test_status_hasil_di_luar_daftar_versi_422(svc, sumber):
    k = _kasus(svc)
    with pytest.raises(ValidationAppError):
        _versi(svc, k, sumber, status=S.TEAM_VERIFIED)


def test_event_menuju_review_butuh_teks(svc):
    k = _kasus(svc)
    _versi(svc, k, None, status=S.NEED_FACT, teks=None)
    v = svc._versi_terbaru(k.id)
    with pytest.raises(ValidationAppError):
        svc.catat_event(k.id, v.id, EventKind.TEAM_REVISE, TIM, None)


def test_trigger_menolak_update_delete_event(svc, db_session, sumber):
    k = _kasus(svc)
    v = _versi(svc, k, sumber)
    e = svc.catat_event(k.id, v.id, EventKind.TEAM_APPROVE, TIM, None)
    with pytest.raises(DBAPIError, match="append-only"), db_session.begin_nested():
        db_session.execute(
            text("UPDATE narasi_event SET event_notes = 'x' WHERE id = :i"), {"i": e.id}
        )
    with pytest.raises(DBAPIError, match="append-only"), db_session.begin_nested():
        db_session.execute(text("DELETE FROM narasi_event WHERE id = :i"), {"i": e.id})
