"""Test pengaju umum `ai_usulan` dan penyerapnya (fungsi AI non-narasi).

Klien model tidak pernah dipanggil; hasil run ditutup langsung lewat `SqlAiRunService.tutup`.
Seluruh data sintetis.
"""

from __future__ import annotations

import hashlib
import os
import signal
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from anjab_abk_backend.ai import penyerap_usulan
from anjab_abk_backend.ai.fungsi_p01 import aturan_p01
from anjab_abk_backend.ai.fungsi_p04 import aturan_p04
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR, AiGateway, FungsiAi
from anjab_abk_backend.ai.penyerap_usulan import ATURAN_ISI, serap_usulan, serap_usulan_tertunda
from anjab_abk_backend.ai.redaksi import SumberAi
from anjab_abk_backend.config import Settings
from anjab_abk_backend.errors import ConflictError
from anjab_abk_backend.fitur import FiturNonaktifError
from anjab_abk_backend.models import (
    AiRunModel,
    AiUsulanModel,
    AsyncJobModel,
    NarasiEventModel,
    NarasiKasusModel,
    NarasiVersiModel,
    NarasiVersiSumberModel,
)
from anjab_abk_backend.narasi import penyerap
from anjab_abk_backend.schemas.ai_run import StatusQaAi
from anjab_abk_backend.schemas.ai_usulan import HasilSerapUsulan, SasaranUsulan
from anjab_abk_backend.security import Principal
from anjab_abk_backend.services.ai_run import hash_masukan
from anjab_abk_backend.services.ai_run_sql import SqlAiRunService
from anjab_abk_backend.services.ai_usulan_sql import SqlAiUsulanService

pytestmark = pytest.mark.usefixtures("penyedia_api")

_HIDUP = Settings(_env_file=None, feature_ai_narrative_draft=True)
_MATI = Settings(_env_file=None, feature_ai_narrative_draft=False)
_SAMARKAN = Settings(_env_file=None, feature_ai_narrative_draft=True, ai_pii_mode="SAMARKAN")
_TEKS = "Guru mengajar kelas lima setiap hari."
_FUNGSI = FungsiAi(
    kode="UJI",
    prompt_version="v1",
    instruksi="Ringkas sumber.",
    skema_isi={"type": "object"},
)
_REG = {_FUNGSI.kode: _FUNGSI}
_PRINCIPAL = Principal(subject="tim-1")
_SASARAN = str(uuid.uuid4())


@pytest.fixture
def fab(db_session: Session):
    @contextmanager
    def _fab() -> Iterator[Session]:
        yield db_session

    return _fab


def _sha(teks: str) -> str:
    return hashlib.sha256(teks.encode("utf-8")).hexdigest()


def _sumber() -> SumberAi:
    return SumberAi(source_id="s1", source_hash=_sha(_TEKS), jenis="SINTETIS", teks=_TEKS)


def _ajukan(
    db: Session,
    settings: Settings = _HIDUP,
    fungsi: str = "UJI",
    sasaran_id: str | None = None,
    registri: dict[str, FungsiAi] | None = None,
):
    gateway = AiGateway(db, settings, registri=_REG if registri is None else registri)
    return SqlAiUsulanService(db, settings, gateway).ajukan(
        fungsi,
        SasaranUsulan.NARASI_KASUS,
        sasaran_id or _SASARAN,
        [_sumber()],
        {"topik": "umum"},
        _PRINCIPAL,
    )


def _keluaran(status: str = "AI_DRAFT", isi: Any = None) -> dict[str, Any]:
    return {
        "status": status,
        "source_refs": [{"source_id": "s1", "source_hash": _sha(_TEKS)}],
        "cited_spans": [{"source_id": "s1", "span": "mengajar kelas lima"}],
        "confidence_reason": "alasan",
        "unknowns": ["jam"],
        "contradictions": [],
        "human_review_required": True,
        "isi": {"ringkas": "Guru mengajar."} if isi is None else isi,
        "kunci_lain": "tidak disimpan di amplop",
    }


def _tutup(
    db: Session,
    ai_run_id: str,
    status: StatusQaAi,
    kode: list[str] | None = None,
    keluaran: dict[str, Any] | None = None,
) -> None:
    runs = SqlAiRunService(db, _HIDUP)
    runs.tutup(ai_run_id, status, kode or [], keluaran, None, None, None, None)


def _rec(db: Session, usulan_id: str) -> AiUsulanModel:
    db.flush()
    db.expire_all()
    return db.get(AiUsulanModel, usulan_id)


def _hitung(db: Session, model: type) -> int:
    db.flush()
    return db.scalar(select(func.count()).select_from(model))


def _jumlah_baris(db: Session) -> tuple[int, int, int]:
    return (_hitung(db, AiUsulanModel), _hitung(db, AiRunModel), _hitung(db, AsyncJobModel))


# --- pengajuan ----------------------------------------------------------------------------


def test_ajukan_mencatat_usulan_belum_diserap_dengan_run_dari_ref_id(db_session):
    u = _ajukan(db_session)
    rec = _rec(db_session, u.id)
    job = db_session.get(AsyncJobModel, u.job_id)
    assert rec.ai_run_id == job.ref_id and db_session.get(AiRunModel, rec.ai_run_id) is not None
    assert (rec.fungsi, rec.sasaran_jenis, rec.sasaran_id) == ("UJI", "NARASI_KASUS", _SASARAN)
    assert rec.sumber_ids == ["s1"] and rec.diminta_oleh == "tim-1"
    assert rec.diserap_at is None and rec.hasil_serap is None and rec.isi is None
    assert not hasattr(u, "isi") and not hasattr(u, "amplop") and not hasattr(u, "output_hash")


def test_flag_mati_409_feature_disabled_nol_baris(db_session):
    sebelum = _jumlah_baris(db_session)
    with pytest.raises(FiturNonaktifError) as e:
        _ajukan(db_session, settings=_MATI)
    assert e.value.error_code == "feature_disabled"
    assert _jumlah_baris(db_session) == sebelum


@pytest.mark.parametrize(
    ("settings", "fungsi", "kode"),
    [
        (_SAMARKAN, "UJI", "pii_mode_belum_didukung"),
        (_HIDUP, "TAK_TERDAFTAR", "fungsi_belum_aktif"),
    ],
    ids=["pii_samarkan", "fungsi_tak_terdaftar"],
)
def test_penolakan_409_sesuai_kode_nol_baris(db_session, settings, fungsi, kode):
    sebelum = _jumlah_baris(db_session)
    with pytest.raises(ConflictError) as e:
        _ajukan(db_session, settings=settings, fungsi=fungsi)
    assert e.value.error_code == kode
    assert _jumlah_baris(db_session) == sebelum


def test_usulan_sama_belum_diserap_409_usulan_berjalan_lalu_lepas_setelah_serap(db_session):
    u = _ajukan(db_session)
    sebelum = _jumlah_baris(db_session)
    with pytest.raises(ConflictError) as e:
        _ajukan(db_session)
    assert e.value.error_code == "usulan_berjalan"
    assert _jumlah_baris(db_session) == sebelum
    # sasaran lain tidak terhalang
    _ajukan(db_session, sasaran_id=str(uuid.uuid4()))
    _tutup(db_session, _rec(db_session, u.id).ai_run_id, StatusQaAi.KARANTINA, ["TANPA_SITASI"])
    assert serap_usulan(db_session, u.id) is HasilSerapUsulan.MANUAL
    _ajukan(db_session)  # tidak lagi tertahan


def test_registri_bawaan_kosong_dan_aturan_isi_hanya_p04():
    assert FUNGSI_TERDAFTAR == {} and ATURAN_ISI == {"P01": aturan_p01, "P04": aturan_p04}


# --- penyerapan ---------------------------------------------------------------------------


def _isi_hijau() -> dict[str, Any]:
    return _keluaran()


def _lolos_aturan_melapor(monkeypatch) -> dict[str, Any]:
    monkeypatch.setitem(ATURAN_ISI, "UJI", lambda isi, amplop: ["ISI_TAK_SAH", "LAIN"])
    return _keluaran()


def _lolos_aturan_meledak(monkeypatch) -> dict[str, Any]:
    def _meledak(isi: dict[str, Any], amplop: dict[str, Any]) -> list[str]:
        raise RuntimeError("galat aturan")

    monkeypatch.setitem(ATURAN_ISI, "UJI", _meledak)
    return _keluaran()


_HASIL_AKHIR = [
    ("USULAN_DIBUAT", StatusQaAi.LOLOS, [], lambda mp: _isi_hijau(), "USULAN_DIBUAT", None),
    (
        "EVIDENCE_GAP_dengan_keluaran",
        StatusQaAi.EVIDENCE_GAP,
        [],
        lambda mp: _keluaran("EVIDENCE_GAP"),
        "EVIDENCE_GAP",
        None,
    ),
    (
        "EVIDENCE_GAP_tanpa_keluaran",
        StatusQaAi.EVIDENCE_GAP,
        ["SUMBER_KOSONG"],
        lambda mp: None,
        "EVIDENCE_GAP",
        None,
    ),
    (
        "MANUAL_KARANTINA",
        StatusQaAi.KARANTINA,
        ["TANPA_SITASI"],
        lambda mp: None,
        "MANUAL",
        ["TANPA_SITASI"],
    ),
    (
        "MANUAL_DIBLOKIR",
        StatusQaAi.DIBLOKIR,
        ["PII_DITEMUKAN"],
        lambda mp: None,
        "MANUAL",
        ["PII_DITEMUKAN"],
    ),
    (
        "MANUAL_GAGAL",
        StatusQaAi.GAGAL,
        ["MODEL_PERMANEN"],
        lambda mp: None,
        "MANUAL",
        ["MODEL_PERMANEN"],
    ),
    (
        "MANUAL_PENYEDIA_MATI",
        StatusQaAi.GAGAL,
        ["PENYEDIA_MATI"],
        lambda mp: None,
        "MANUAL",
        ["PENYEDIA_MATI"],
    ),
    (
        "MANUAL_PENYEDIA_TIDAK_TERSEDIA",
        StatusQaAi.GAGAL,
        ["PENYEDIA_TIDAK_TERSEDIA"],
        lambda mp: None,
        "MANUAL",
        ["PENYEDIA_TIDAK_TERSEDIA"],
    ),
    (
        "MANUAL_LANGGANAN_BELUM_MASUK",
        StatusQaAi.GAGAL,
        ["LANGGANAN_BELUM_MASUK"],
        lambda mp: None,
        "MANUAL",
        ["LANGGANAN_BELUM_MASUK"],
    ),
    (
        "MANUAL_ATURAN_ISI",
        StatusQaAi.LOLOS,
        [],
        _lolos_aturan_melapor,
        "MANUAL",
        ["ISI_TAK_SAH", "LAIN"],
    ),
    (
        "MANUAL_ATURAN_ISI_MELEDAK",
        StatusQaAi.LOLOS,
        [],
        _lolos_aturan_meledak,
        "MANUAL",
        ["GALAT_SERAP"],
    ),
    (
        "MANUAL_KELUARAN_TIDAK_SAH",
        StatusQaAi.LOLOS,
        [],
        lambda mp: {"status": "AI_DRAFT", "isi": "bukan objek"},
        "MANUAL",
        ["KELUARAN_TIDAK_SAH"],
    ),
]


@pytest.mark.parametrize(
    ("nama", "status", "kode", "buat", "hasil", "kode_serap"),
    _HASIL_AKHIR,
    ids=[c[0] for c in _HASIL_AKHIR],
)
def test_hasil_akhir_mengisi_diserap_at_dan_hasil_serap(
    db_session, monkeypatch, nama, status, kode, buat, hasil, kode_serap
):
    u = _ajukan(db_session)
    _tutup(db_session, _rec(db_session, u.id).ai_run_id, status, kode, buat(monkeypatch))

    assert serap_usulan(db_session, u.id) is HasilSerapUsulan(hasil)

    rec = _rec(db_session, u.id)
    assert rec.diserap_at is not None
    assert rec.hasil_serap == hasil and rec.kode_serap == kode_serap
    if hasil == "MANUAL":
        assert rec.isi is None and rec.output_hash is None


def test_run_menunggu_tidak_diserap(db_session, fab):
    u = _ajukan(db_session)
    assert serap_usulan(db_session, u.id) is None
    assert serap_usulan_tertunda(fab) == 0
    rec = _rec(db_session, u.id)
    assert rec.diserap_at is None and rec.hasil_serap is None


def test_lolos_menyimpan_isi_amplop_dan_output_hash(db_session):
    u = _ajukan(db_session)
    kel = _keluaran()
    _tutup(db_session, _rec(db_session, u.id).ai_run_id, StatusQaAi.LOLOS, None, kel)
    serap_usulan(db_session, u.id)
    rec = _rec(db_session, u.id)
    assert rec.isi == kel["isi"]
    assert set(rec.amplop) == {
        "source_refs",
        "cited_spans",
        "confidence_reason",
        "unknowns",
        "contradictions",
    }
    assert rec.output_hash == hash_masukan(kel)


def test_evidence_gap_dengan_keluaran_mengisi_amplop_tanpa_isi(db_session):
    u = _ajukan(db_session)
    _tutup(
        db_session,
        _rec(db_session, u.id).ai_run_id,
        StatusQaAi.EVIDENCE_GAP,
        None,
        _keluaran("EVIDENCE_GAP"),
    )
    serap_usulan(db_session, u.id)
    rec = _rec(db_session, u.id)
    assert rec.amplop is not None and rec.isi is None


def test_serap_dua_kali_tanpa_perubahan_kedua(db_session):
    u = _ajukan(db_session)
    _tutup(db_session, _rec(db_session, u.id).ai_run_id, StatusQaAi.LOLOS, None, _keluaran())
    assert serap_usulan(db_session, u.id) is HasilSerapUsulan.USULAN_DIBUAT
    pertama = _rec(db_session, u.id).diserap_at
    assert serap_usulan(db_session, u.id) is None
    assert _rec(db_session, u.id).diserap_at == pertama
    assert _hitung(db_session, AiUsulanModel) == 1


def test_klaim_memakai_for_update_skip_locked_untuk_dua_penyerap(db_session, monkeypatch):
    """Dua penyerap bersamaan: klaim `SKIP LOCKED` + guard `diserap_at IS NULL`."""
    u = _ajukan(db_session)
    _tutup(db_session, _rec(db_session, u.id).ai_run_id, StatusQaAi.LOLOS, None, _keluaran())
    kalimat: list[str] = []

    def _tangkap(conn, cursor, statement, *_a):
        kalimat.append(statement)

    event.listen(db_session.get_bind(), "before_cursor_execute", _tangkap)
    try:
        serap_usulan(db_session, u.id)
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", _tangkap)
    klaim = [k for k in kalimat if "FROM ai_usulan" in k and "FOR UPDATE" in k]
    assert klaim and all("SKIP LOCKED" in k and "diserap_at IS NULL" in k for k in klaim)


def test_satu_usulan_bermasalah_tidak_menghentikan_loop(db_session, fab, monkeypatch):
    buruk = _ajukan(db_session, sasaran_id=str(uuid.uuid4()))
    baik = _ajukan(db_session, sasaran_id=str(uuid.uuid4()))
    for u in (buruk, baik):
        _tutup(db_session, _rec(db_session, u.id).ai_run_id, StatusQaAi.LOLOS, None, _keluaran())
    asli = penyerap_usulan.serap_usulan

    def _meledak_sekali(session, uid):
        if uid == buruk.id and not getattr(_meledak_sekali, "sudah", False):
            _meledak_sekali.sudah = True
            raise RuntimeError("galat tak terduga")
        return asli(session, uid)

    monkeypatch.setattr(penyerap_usulan, "serap_usulan", _meledak_sekali)
    urutan = sorted([buruk, baik], key=lambda x: x.id)
    assert urutan  # kedua usulan ada
    assert serap_usulan_tertunda(fab) == 1
    assert _rec(db_session, baik.id).diserap_at is not None
    assert serap_usulan_tertunda(fab) == 1
    assert _rec(db_session, buruk.id).diserap_at is not None
    assert serap_usulan_tertunda(fab) == 0


def test_serap_usulan_hanya_menulis_ai_usulan_tanpa_tabel_narasi(db_session):
    u = _ajukan(db_session)
    _tutup(db_session, _rec(db_session, u.id).ai_run_id, StatusQaAi.LOLOS, None, _keluaran())
    db_session.flush()
    ditulis: list[str] = []

    def _catat(session: Session, _ctx: Any, _inst: Any) -> None:
        ditulis.extend(type(o).__name__ for o in (*session.new, *session.dirty, *session.deleted))

    event.listen(db_session, "before_flush", _catat)
    try:
        serap_usulan(db_session, u.id)
        db_session.flush()
    finally:
        event.remove(db_session, "before_flush", _catat)
    assert set(ditulis) == {"AiUsulanModel"}
    for model in (NarasiEventModel, NarasiVersiModel, NarasiVersiSumberModel, NarasiKasusModel):
        assert _hitung(db_session, model) == 0


def test_run_p10_tanpa_usulan_tidak_disentuh_dan_tidak_membuat_ai_usulan(db_session, fab):
    runs = SqlAiRunService(db_session, _HIDUP)
    run = runs.buka("P10", "p10-1", hash_masukan("p"), "claude-x", [], {"parameter": {}})
    runs.tutup(run.id, StatusQaAi.LOLOS, [], _keluaran(), None, None, None, None)
    assert serap_usulan_tertunda(fab) == 0
    assert _hitung(db_session, AiUsulanModel) == 0


# --- integrasi loop penyerap ---------------------------------------------------------------


def test_main_memanggil_serap_usulan_meski_serap_tertunda_gagal(monkeypatch):
    monkeypatch.setattr(
        penyerap,
        "get_settings",
        lambda: Settings(_env_file=None, feature_ai_narrative_draft=True, ai_worker_poll_detik=1),
    )
    panggilan: list[str] = []

    def _narasi_gagal(_fabrik):
        panggilan.append("narasi")
        raise RuntimeError("galat narasi")

    def _usulan(_fabrik):
        panggilan.append("usulan")
        os.kill(os.getpid(), signal.SIGTERM)
        return 0

    monkeypatch.setattr(penyerap, "serap_tertunda", _narasi_gagal)
    monkeypatch.setattr(penyerap, "serap_usulan_tertunda", _usulan)
    asli_term = signal.getsignal(signal.SIGTERM)
    asli_int = signal.getsignal(signal.SIGINT)
    try:
        assert penyerap.main() == 0
    finally:
        signal.signal(signal.SIGTERM, asli_term)
        signal.signal(signal.SIGINT, asli_int)
    assert panggilan == ["narasi", "usulan"]
