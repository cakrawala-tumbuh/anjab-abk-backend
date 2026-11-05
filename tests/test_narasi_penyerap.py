"""Tes penyerap hasil run AI ke versi narasi (`narasi/penyerap.py`).

Data sintetis; tidak ada klien model dan tidak ada jaringan.
"""

from __future__ import annotations

import hashlib
import uuid
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from anjab_abk_backend.config import Settings
from anjab_abk_backend.models import (
    AiRunModel,
    NarasiAiPermintaanModel,
    NarasiEventModel,
    NarasiKasusModel,
    NarasiSumberModel,
    NarasiVersiModel,
    NarasiVersiSumberModel,
)
from anjab_abk_backend.narasi import penyerap
from anjab_abk_backend.narasi.penyerap import HasilSerap, serap_run, serap_tertunda
from anjab_abk_backend.narasi.schemas.kasus import RevisionOrigin, StatusNarasi
from anjab_abk_backend.narasi.schemas.mesin import (
    AKTOR_AI_WORKER,
    AktorNarasi,
    KutipanSumber,
    NarasiKasusCreate,
)
from anjab_abk_backend.narasi.schemas.permintaan_ai import PermintaanAiRead
from anjab_abk_backend.narasi.services.narasi import VersiBasiError
from anjab_abk_backend.narasi.services.narasi_sql import SqlNarasiService
from anjab_abk_backend.narasi.services.permintaan_ai_sql import SqlPermintaanAiService
from anjab_abk_backend.schemas.ai_run import AiRunRead, AiSumber, StatusQaAi
from anjab_abk_backend.services.ai_run import hash_masukan
from anjab_abk_backend.services.ai_run_sql import SqlAiRunService

_CFG = Settings(_env_file=None)
TIM = AktorNarasi(key="tim-1", role="REVIEWER")
_TEKS = "Guru mengajar kelas lima setiap hari."
S = StatusNarasi


@pytest.fixture
def fab(db_session: Session):
    @contextmanager
    def _fab():
        yield db_session

    return _fab


@pytest.fixture
def sumber(db_session: Session) -> NarasiSumberModel:
    rec = NarasiSumberModel(
        id=str(uuid.uuid4()),
        judul="j",
        jenis="SINTETIS",
        versi="v1",
        periode="2026-27",
        teks=_TEKS,
        teks_hash=hashlib.sha256(_TEKS.encode()).hexdigest(),
        dibuat_oleh="t",
    )
    db_session.add(rec)
    db_session.flush()
    return rec


def _kasus(db: Session):
    return SqlNarasiService(db).buat_kasus(
        NarasiKasusCreate(
            instrument_id="wcp",
            field_key=f"f-{uuid.uuid4().hex[:8]}",
            peran_ref="guru",
            periode="2026-27",
            narrative_kind="F1_FORMAL",
            intended_use="uji",
            permission_scope="tim",
            sensitivity_class="NONPRIBADI",
        ),
        TIM,
    )


def _keluaran(
    sumber: NarasiSumberModel,
    status: str = "AI_DRAFT",
    draft: str | None = "Guru mengajar kelas lima.",
    spans: bool = True,
) -> dict[str, Any]:
    return {
        "status": status,
        "source_refs": [{"source_id": sumber.id, "source_hash": sumber.teks_hash}],
        "cited_spans": [{"source_id": sumber.id, "span": "mengajar kelas lima"}] if spans else [],
        "confidence_reason": "alasan",
        "unknowns": ["jam"] if status == "EVIDENCE_GAP" else [],
        "contradictions": [],
        "human_review_required": True,
        "isi": {
            "narrative_kind": "F1_FORMAL",
            "draft_text": draft,
            "claim_to_source_map": [],
            "missing_facts": ["volume"] if status == "EVIDENCE_GAP" else [],
            "recommended_review_scope": "semua",
            "label_dokumenter": "DOCUMENTARY_CANDIDATE",
        },
    }


def _permintaan(
    db: Session,
    kasus_id: str,
    sumber: NarasiSumberModel,
    status: StatusQaAi | None,
    kode: list[str] | None = None,
    keluaran: dict[str, Any] | None = None,
) -> tuple[PermintaanAiRead, str]:
    """Buka run (ditutup bila ``status`` bukan None) lalu catat permintaannya."""
    runs = SqlAiRunService(db, _CFG)
    run = runs.buka(
        "P10",
        "p10-1",
        hash_masukan("prompt"),
        "claude-x",
        [AiSumber(source_id=sumber.id, source_hash=sumber.teks_hash)],
        {"sumber": [], "parameter": {}, "ref_id": None},
    )
    if status is not None:
        runs.tutup(run.id, status, kode or [], keluaran, None, None, None, None)
    p = SqlPermintaanAiService(db).catat(kasus_id, str(uuid.uuid4()), run.id, [sumber.id], "tim-1")
    return p, run.id


def _versi(db: Session, kasus_id: str) -> list[NarasiVersiModel]:
    db.flush()
    db.expire_all()
    return list(
        db.scalars(select(NarasiVersiModel).where(NarasiVersiModel.narasi_id == kasus_id)).all()
    )


def _status(db: Session, kasus_id: str) -> str:
    db.flush()
    db.expire_all()
    return db.get(NarasiKasusModel, kasus_id).status


def _rec(db: Session, pid: str) -> NarasiAiPermintaanModel:
    db.flush()
    db.expire_all()
    return db.get(NarasiAiPermintaanModel, pid)


# --- positif & idempoten -----------------------------------------------------------------


def test_lolos_membuat_versi_ai_draft_dengan_run_hash_dan_sumber(db_session, sumber):
    k = _kasus(db_session)
    kel = _keluaran(sumber)
    p, run_id = _permintaan(db_session, k.id, sumber, StatusQaAi.LOLOS, keluaran=kel)

    assert serap_run(db_session, p.id) is HasilSerap.VERSI_DIBUAT

    (v,) = _versi(db_session, k.id)
    assert v.revision_origin == "AI_DRAFT" and v.status_hasil == "AI_DRAFT"
    assert v.teks == kel["isi"]["draft_text"] and v.ai_run_id == run_id
    assert v.output_hash == hash_masukan(kel) and v.supersedes_id is None
    assert v.dibuat_oleh == AKTOR_AI_WORKER
    assert set(v.metadata_ai) <= {
        "claim_to_source_map",
        "missing_facts",
        "contradictions",
        "unknowns",
        "recommended_review_scope",
        "label_dokumenter",
        "confidence_reason",
    }
    (tautan,) = db_session.scalars(
        select(NarasiVersiSumberModel).where(NarasiVersiSumberModel.narasi_versi_id == v.id)
    ).all()
    assert tautan.sumber_id == sumber.id and tautan.basis_relation == "DIRECT"
    assert tautan.source_hash == sumber.teks_hash
    assert _status(db_session, k.id) == "AI_DRAFT"
    rec = _rec(db_session, p.id)
    assert rec.hasil_serap == "VERSI_DIBUAT" and rec.diserap_at is not None


def test_serap_dua_kali_tetap_satu_versi(db_session, sumber):
    k = _kasus(db_session)
    p, _ = _permintaan(db_session, k.id, sumber, StatusQaAi.LOLOS, keluaran=_keluaran(sumber))
    assert serap_run(db_session, p.id) is HasilSerap.VERSI_DIBUAT
    assert serap_run(db_session, p.id) is None
    assert len(_versi(db_session, k.id)) == 1


def test_pagar_kedua_ai_run_id_unik_bila_penanda_hilang(db_session, sumber):
    k = _kasus(db_session)
    p, _ = _permintaan(db_session, k.id, sumber, StatusQaAi.LOLOS, keluaran=_keluaran(sumber))
    serap_run(db_session, p.id)
    rec = _rec(db_session, p.id)
    rec.diserap_at = None
    rec.hasil_serap = None
    db_session.flush()
    assert serap_run(db_session, p.id) is HasilSerap.VERSI_DIBUAT
    assert len(_versi(db_session, k.id)) == 1


def test_run_menunggu_dilewati_dan_tetap_menahan_kasus(db_session, sumber, fab):
    k = _kasus(db_session)
    p, _ = _permintaan(db_session, k.id, sumber, None)
    assert serap_run(db_session, p.id) is None
    assert serap_tertunda(fab) == 0
    assert _rec(db_session, p.id).diserap_at is None
    assert SqlPermintaanAiService(db_session).ada_belum_diserap(k.id) is True


# --- EVIDENCE_GAP ------------------------------------------------------------------------


def test_gap_dengan_keluaran_menjadi_need_fact_teks_null(db_session, sumber):
    k = _kasus(db_session)
    kel = _keluaran(sumber, status="EVIDENCE_GAP", draft=None, spans=False)
    p, _ = _permintaan(db_session, k.id, sumber, StatusQaAi.EVIDENCE_GAP, keluaran=kel)
    assert serap_run(db_session, p.id) is HasilSerap.NEED_FACT
    (v,) = _versi(db_session, k.id)
    assert v.status_hasil == "NEED_FACT" and v.teks is None
    assert v.metadata_ai["missing_facts"] == ["volume"]
    assert v.output_hash == hash_masukan(kel)
    assert _status(db_session, k.id) == "NEED_FACT"


def test_gap_sumber_kosong_tanpa_keluaran_output_hash_null(db_session, sumber):
    k = _kasus(db_session)
    p, _ = _permintaan(db_session, k.id, sumber, StatusQaAi.EVIDENCE_GAP, ["SUMBER_KOSONG"])
    assert serap_run(db_session, p.id) is HasilSerap.NEED_FACT
    (v,) = _versi(db_session, k.id)
    assert v.status_hasil == "NEED_FACT" and v.teks is None and v.output_hash is None
    assert v.metadata_ai == {"missing_facts": ["SUMBER_KOSONG"]}


# --- negatif -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "kode"),
    [
        (StatusQaAi.KARANTINA, ["TANPA_SITASI"]),
        (StatusQaAi.DIBLOKIR, ["PII_DITEMUKAN"]),
        (StatusQaAi.GAGAL, ["MODEL_PERMANEN"]),
        (StatusQaAi.GAGAL, ["PENYEDIA_MATI"]),
        (StatusQaAi.GAGAL, ["PENYEDIA_TIDAK_TERSEDIA"]),
        (StatusQaAi.GAGAL, ["LANGGANAN_BELUM_MASUK"]),
    ],
)
def test_run_bermasalah_tanpa_versi_kasus_tetap_kode_serap_dari_kode_qa(
    db_session, sumber, status, kode
):
    k = _kasus(db_session)
    p, _ = _permintaan(db_session, k.id, sumber, status, kode)
    assert serap_run(db_session, p.id) is HasilSerap.MANUAL
    assert _versi(db_session, k.id) == [] and _status(db_session, k.id) == "SOURCE_CHECKED"
    rec = _rec(db_session, p.id)
    assert rec.hasil_serap == "MANUAL" and rec.kode_serap == kode


@pytest.mark.parametrize(
    ("status", "kel"),
    [
        (StatusQaAi.LOLOS, lambda s: _keluaran(s, draft=None)),
        (StatusQaAi.LOLOS, lambda s: _keluaran(s, draft="   ")),
        (StatusQaAi.EVIDENCE_GAP, lambda s: _keluaran(s, status="EVIDENCE_GAP", draft="ada")),
    ],
)
def test_pelanggaran_draft_text_aturan_snd_dilanggar(db_session, sumber, status, kel):
    k = _kasus(db_session)
    p, _ = _permintaan(db_session, k.id, sumber, status, keluaran=kel(sumber))
    assert serap_run(db_session, p.id) is HasilSerap.MANUAL
    assert _versi(db_session, k.id) == [] and _status(db_session, k.id) == "SOURCE_CHECKED"
    assert _rec(db_session, p.id).kode_serap == ["ATURAN_SND_DILANGGAR"]


def test_kasus_sudah_direvisi_manual_kasus_berubah(db_session, sumber):
    svc = SqlNarasiService(db_session)
    k = _kasus(db_session)
    v = svc.tambah_versi(
        k.id,
        revision_origin=RevisionOrigin.REVIEWER_EDIT,
        status_hasil=S.TEAM_REVIEW,
        teks="isi",
        sumber=[
            KutipanSumber(
                sumber_id=sumber.id, source_hash=sumber.teks_hash, basis_relation="DIRECT"
            )
        ],
        supersedes_id=None,
        aktor=TIM,
    )
    p, _ = _permintaan(db_session, k.id, sumber, StatusQaAi.LOLOS, keluaran=_keluaran(sumber))
    assert serap_run(db_session, p.id) is HasilSerap.MANUAL
    assert [x.id for x in _versi(db_session, k.id)] == [v.id]
    assert _status(db_session, k.id) == "TEAM_REVIEW"
    assert _rec(db_session, p.id).kode_serap == ["KASUS_BERUBAH"]


# --- galat tambah_versi: tidak menahan kasus, tidak menghentikan loop ---------------------


def test_versi_basi_dari_tambah_versi_menjadi_kasus_berubah(db_session, sumber, monkeypatch):
    k = _kasus(db_session)
    p, _ = _permintaan(db_session, k.id, sumber, StatusQaAi.LOLOS, keluaran=_keluaran(sumber))

    def _basi(*_a: Any, **_k: Any):
        raise VersiBasiError("basi")

    monkeypatch.setattr(SqlNarasiService, "tambah_versi", _basi)
    assert serap_run(db_session, p.id) is HasilSerap.MANUAL
    assert _rec(db_session, p.id).kode_serap == ["KASUS_BERUBAH"]
    assert _versi(db_session, k.id) == []


def test_no_source_no_fact_dan_hash_tak_cocok_versi_ditolak(db_session, sumber):
    k1, k2 = _kasus(db_session), _kasus(db_session)
    tanpa_sitasi = _keluaran(sumber, spans=False)
    p1, _ = _permintaan(db_session, k1.id, sumber, StatusQaAi.LOLOS, keluaran=tanpa_sitasi)
    hash_salah = _keluaran(sumber)
    hash_salah["source_refs"][0]["source_hash"] = "0" * 64
    p2, _ = _permintaan(db_session, k2.id, sumber, StatusQaAi.LOLOS, keluaran=hash_salah)
    assert serap_run(db_session, p1.id) is HasilSerap.MANUAL
    assert serap_run(db_session, p2.id) is HasilSerap.MANUAL
    assert _rec(db_session, p1.id).kode_serap == ["VERSI_DITOLAK"]
    assert _rec(db_session, p2.id).kode_serap == ["VERSI_DITOLAK"]
    assert _versi(db_session, k1.id) == [] and _versi(db_session, k2.id) == []


def test_satu_permintaan_bermasalah_tidak_menghentikan_serap_tertunda(
    db_session, sumber, fab, monkeypatch
):
    k_buruk, k_baik = _kasus(db_session), _kasus(db_session)
    buruk = _keluaran(sumber, spans=False)
    p_buruk, _ = _permintaan(db_session, k_buruk.id, sumber, StatusQaAi.LOLOS, keluaran=buruk)
    p_baik, _ = _permintaan(
        db_session, k_baik.id, sumber, StatusQaAi.LOLOS, keluaran=_keluaran(sumber)
    )
    asli = penyerap.serap_run
    panggilan: list[str] = []

    def _meledak_sekali(session, pid):
        panggilan.append(pid)
        if pid == p_buruk.id and panggilan.count(pid) == 1:
            raise RuntimeError("galat tak terduga")
        return asli(session, pid)

    monkeypatch.setattr(penyerap, "serap_run", _meledak_sekali)
    assert serap_tertunda(fab) == 1
    assert _rec(db_session, p_baik.id).hasil_serap == "VERSI_DIBUAT"
    assert serap_tertunda(fab) == 1
    assert _rec(db_session, p_buruk.id).kode_serap == ["VERSI_DITOLAK"]
    assert serap_tertunda(fab) == 0


# --- bukti: semua hasil akhir menandai diserap_at dan melepas kasus -----------------------


def _kasus_berubah(db: Session, sumber: NarasiSumberModel, kasus_id: str) -> None:
    SqlNarasiService(db).tambah_versi(
        kasus_id,
        revision_origin=RevisionOrigin.REVIEWER_EDIT,
        status_hasil=S.TEAM_REVIEW,
        teks="isi",
        sumber=[
            KutipanSumber(
                sumber_id=sumber.id, source_hash=sumber.teks_hash, basis_relation="DIRECT"
            )
        ],
        supersedes_id=None,
        aktor=TIM,
    )


_KASUS_HASIL_AKHIR = [
    ("VERSI_DIBUAT", StatusQaAi.LOLOS, [], lambda s: _keluaran(s), False),
    (
        "NEED_FACT_dengan_keluaran",
        StatusQaAi.EVIDENCE_GAP,
        [],
        lambda s: _keluaran(s, status="EVIDENCE_GAP", draft=None, spans=False),
        False,
    ),
    ("NEED_FACT_tanpa_keluaran", StatusQaAi.EVIDENCE_GAP, ["SUMBER_KOSONG"], lambda s: None, False),
    ("MANUAL_KARANTINA", StatusQaAi.KARANTINA, ["TANPA_SITASI"], lambda s: None, False),
    ("MANUAL_DIBLOKIR", StatusQaAi.DIBLOKIR, ["PII_DITEMUKAN"], lambda s: None, False),
    ("MANUAL_GAGAL", StatusQaAi.GAGAL, ["MODEL_PERMANEN"], lambda s: None, False),
    (
        "MANUAL_ATURAN_SND_DILANGGAR",
        StatusQaAi.LOLOS,
        [],
        lambda s: _keluaran(s, draft=None),
        False,
    ),
    ("MANUAL_KASUS_BERUBAH", StatusQaAi.LOLOS, [], lambda s: _keluaran(s), True),
]


@pytest.mark.parametrize(
    ("nama", "status", "kode", "buat_keluaran", "kasus_berubah"),
    _KASUS_HASIL_AKHIR,
    ids=[c[0] for c in _KASUS_HASIL_AKHIR],
)
def test_hasil_akhir_mengisi_diserap_at_dan_melepas_kasus(
    db_session, sumber, nama, status, kode, buat_keluaran, kasus_berubah
):
    k = _kasus(db_session)
    if kasus_berubah:
        _kasus_berubah(db_session, sumber, k.id)
    p, _ = _permintaan(db_session, k.id, sumber, status, kode, buat_keluaran(sumber))
    assert SqlPermintaanAiService(db_session).ada_belum_diserap(k.id) is True

    assert serap_run(db_session, p.id) is not None

    assert _rec(db_session, p.id).diserap_at is not None
    assert SqlPermintaanAiService(db_session).ada_belum_diserap(k.id) is False


# --- batas: tanpa event, tanpa rute, tanpa keluaran, flag mati ---------------------------


def test_penyerap_tidak_menulis_narasi_event(db_session, sumber):
    k = _kasus(db_session)
    p, _ = _permintaan(db_session, k.id, sumber, StatusQaAi.LOLOS, keluaran=_keluaran(sumber))
    ditulis: list[str] = []

    def _catat(session: Session, _ctx: Any, _inst: Any) -> None:
        ditulis.extend(type(o).__name__ for o in (*session.new, *session.dirty, *session.deleted))

    event.listen(db_session, "before_flush", _catat)
    try:
        serap_run(db_session, p.id)
    finally:
        event.remove(db_session, "before_flush", _catat)
    assert "NarasiVersiModel" in ditulis and "NarasiEventModel" not in ditulis
    assert db_session.scalar(select(func.count()).select_from(NarasiEventModel)) == 0


def test_ai_run_read_tanpa_keluaran_dan_openapi_tanpa_rute_baru(app):
    assert "keluaran" not in AiRunRead.model_fields and "masukan" not in AiRunRead.model_fields
    paths = app.openapi()["paths"]
    assert not [p for p in paths if "serap" in p or "penyerap" in p]
    skema = app.openapi()["components"]["schemas"]["AiRunRead"]
    assert "keluaran" not in skema["properties"] and "masukan" not in skema["properties"]


def test_keluaran_internal_salinan_dan_run_tak_ada(db_session, sumber):
    from anjab_abk_backend.errors import NotFoundError

    k = _kasus(db_session)
    kel = _keluaran(sumber)
    _, run_id = _permintaan(db_session, k.id, sumber, StatusQaAi.LOLOS, keluaran=kel)
    svc = SqlAiRunService(db_session, _CFG)
    assert svc.keluaran_internal(run_id) == kel
    _, run_menunggu = _permintaan(db_session, _kasus(db_session).id, sumber, None)
    assert svc.keluaran_internal(run_menunggu) is None
    with pytest.raises(NotFoundError):
        svc.keluaran_internal(str(uuid.uuid4()))
    assert db_session.get(AiRunModel, run_id).keluaran == kel


def test_entrypoint_flag_mati_keluar_kode_nol(monkeypatch):
    monkeypatch.setattr(penyerap, "get_settings", lambda: Settings(_env_file=None))

    def _larang(*_a: Any, **_k: Any):
        raise AssertionError("tidak boleh menyerap saat flag mati")

    monkeypatch.setattr(penyerap, "serap_tertunda", _larang)
    assert penyerap.main() == 0
