"""Test pengaturan penyedia AI: enkripsi, service SQL, event, dan larangan bocor."""

from __future__ import annotations

import logging

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.orm import Session

from anjab_abk_backend.ai.kredensial import (
    KredensialTakTerbaca,
    KunciIndukTidakAda,
    dekripsi_kredensial,
    enkripsi_kredensial,
)
from anjab_abk_backend.ai.penyedia import AI_EFFORT_BAWAAN, AI_MODEL_BAWAAN, AiPenyediaMode
from anjab_abk_backend.config import Settings
from anjab_abk_backend.errors import ConflictError, ValidationAppError
from anjab_abk_backend.logging import AUDIT_LOGGER_NAME
from anjab_abk_backend.models import AiPenyediaEventModel, AiPenyediaPengaturanModel
from anjab_abk_backend.services.ai_penyedia_sql import SqlAiPenyediaService

_KUNCI_API = "kunci-api-sintetis-uji-1234"
_ALASAN = "Alasan uji penyedia"
_AKTOR = "admin@example.test"


def _settings(kunci_induk: str | None) -> Settings:
    return Settings(
        _env_file=None,
        ai_kredensial_kunci_induk=SecretStr(kunci_induk if kunci_induk is not None else ""),
    )


@pytest.fixture
def induk() -> str:
    return Fernet.generate_key().decode()


@pytest.fixture
def svc(db_session: Session, induk: str) -> SqlAiPenyediaService:
    return SqlAiPenyediaService(db_session, _settings(induk))


def test_enkripsi_dekripsi_bolak_balik_ciphertext_tak_memuat_teks_asli(induk: str) -> None:
    sk = SecretStr(induk)
    c = enkripsi_kredensial(sk, _KUNCI_API)
    assert _KUNCI_API not in c
    assert dekripsi_kredensial(sk, c) == _KUNCI_API


def test_dekripsi_kunci_induk_lain_gagal_dan_status_tidak_terbaca(
    db_session: Session, induk: str
) -> None:
    SqlAiPenyediaService(db_session, _settings(induk)).pasang_kredensial(
        _KUNCI_API, _ALASAN, _AKTOR
    )
    lain = SecretStr(Fernet.generate_key().decode())
    c = db_session.get(AiPenyediaPengaturanModel, "TUNGGAL").kredensial_terenkripsi
    with pytest.raises(KredensialTakTerbaca):
        dekripsi_kredensial(lain, c)
    st = SqlAiPenyediaService(
        db_session, Settings(_env_file=None, ai_kredensial_kunci_induk=lain)
    ).status()
    assert st.kredensial_terpasang is True and st.kredensial_terbaca is False


def test_status_awal_bawaan(svc: SqlAiPenyediaService) -> None:
    st = svc.status()
    assert st.mode is AiPenyediaMode.MATI
    assert st.model == AI_MODEL_BAWAAN == "claude-opus-5-5"
    assert st.effort.value == AI_EFFORT_BAWAAN == "high"
    assert st.kredensial_terpasang is False and st.enkripsi_siap is True


def test_pasang_baca_hapus_dan_akhiran(svc: SqlAiPenyediaService, db_session: Session) -> None:
    st = svc.pasang_kredensial(_KUNCI_API, _ALASAN, _AKTOR)
    assert st.kredensial_terpasang and st.kredensial_terbaca
    assert st.kredensial_akhiran == _KUNCI_API[-4:]
    rec = db_session.get(AiPenyediaPengaturanModel, "TUNGGAL")
    assert rec.kredensial_terenkripsi and _KUNCI_API not in rec.kredensial_terenkripsi
    assert svc.baca_kunci_api() == _KUNCI_API
    st = svc.hapus_kredensial(_ALASAN, _AKTOR)
    assert st.kredensial_terpasang is False and st.kredensial_akhiran is None
    assert svc.baca_kunci_api() is None


@pytest.mark.parametrize("induk_buruk", ["", "bukan-kunci-fernet"])
def test_kunci_induk_kosong_atau_salah_menolak_pasang_tanpa_baris(
    db_session: Session, induk_buruk: str
) -> None:
    s = SqlAiPenyediaService(db_session, _settings(induk_buruk))
    assert s.status().enkripsi_siap is False
    with pytest.raises(KunciIndukTidakAda):
        s.pasang_kredensial(_KUNCI_API, _ALASAN, _AKTOR)
    assert db_session.query(AiPenyediaPengaturanModel).count() == 0
    assert db_session.query(AiPenyediaEventModel).count() == 0


def test_ubah_mode_dan_event(svc: SqlAiPenyediaService, db_session: Session) -> None:
    assert svc.ubah_mode(AiPenyediaMode.API_ANTHROPIC, _ALASAN, _AKTOR).mode.value == (
        "API_ANTHROPIC"
    )
    svc.ubah_mode(AiPenyediaMode.LANGGANAN_CLAUDE, _ALASAN, _AKTOR)
    ev = db_session.query(AiPenyediaEventModel).all()
    assert [e.aksi for e in ev] == ["UBAH_MODE", "UBAH_MODE"] or len(ev) == 2
    assert all(e.aktor == _AKTOR and e.alasan == _ALASAN for e in ev)


def test_memilih_penyedia_tidak_menyalakan_ai(svc: SqlAiPenyediaService) -> None:
    from anjab_abk_backend.fitur import ai_boleh_jalan  # noqa: F401  (impor membuktikan ada)

    svc.ubah_mode(AiPenyediaMode.API_ANTHROPIC, _ALASAN, _AKTOR)
    s = Settings(_env_file=None)
    assert s.feature_ai_narrative_draft is False and s.ai_fungsi_aktif == []


def test_ubah_model_dan_effort_event(svc: SqlAiPenyediaService, db_session: Session) -> None:
    st = svc.ubah_model("claude-sonnet-4-6", "low", _ALASAN, _AKTOR)
    assert st.model == "claude-sonnet-4-6" and st.effort.value == "low"
    ev = db_session.query(AiPenyediaEventModel).one()
    assert ev.aksi == "UBAH_MODEL" and ev.model == "claude-sonnet-4-6" and ev.effort == "low"
    st = svc.ubah_model(None, None, _ALASAN, _AKTOR)
    assert st.model == AI_MODEL_BAWAAN


def test_negatif_konflik_dan_penolakan_tanpa_baris_berubah(
    svc: SqlAiPenyediaService, db_session: Session
) -> None:
    with pytest.raises(ConflictError):
        svc.ubah_mode(AiPenyediaMode.MATI, _ALASAN, _AKTOR)
    with pytest.raises(ConflictError):
        svc.hapus_kredensial(_ALASAN, _AKTOR)
    with pytest.raises(ConflictError):
        svc.ubah_model(None, None, _ALASAN, _AKTOR)
    for model, effort in (
        ("claude-fable-x", None),
        ("claude-mythos-1", None),
        ("gpt-4", None),
        (None, "ekstrem"),
    ):
        with pytest.raises(ValidationAppError):
            svc.ubah_model(model, effort, _ALASAN, _AKTOR)
    assert db_session.query(AiPenyediaPengaturanModel).count() == 0
    assert db_session.query(AiPenyediaEventModel).count() == 0


def test_kunci_pendek_ditolak_tanpa_membocorkan(svc: SqlAiPenyediaService) -> None:
    with pytest.raises(ValidationAppError) as e:
        svc.pasang_kredensial("abc", _ALASAN, _AKTOR)
    assert "abc" not in str(e.value)


class _Tangkap(logging.Handler):
    """Penangkap record logger audit untuk pemeriksaan kebocoran."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def test_kredensial_tidak_bocor_ke_log_event_repr_atau_galat(
    svc: SqlAiPenyediaService, db_session: Session, induk: str
) -> None:
    tangkap = _Tangkap()
    audit = logging.getLogger(AUDIT_LOGGER_NAME)
    audit.addHandler(tangkap)
    audit.setLevel(logging.DEBUG)
    try:
        st = svc.pasang_kredensial(_KUNCI_API, _ALASAN, _AKTOR)
        svc.hapus_kredensial(_ALASAN, _AKTOR)
        svc.pasang_kredensial(_KUNCI_API, _ALASAN, _AKTOR)
    finally:
        audit.removeHandler(tangkap)
    rec = db_session.get(AiPenyediaPengaturanModel, "TUNGGAL")
    cipher = rec.kredensial_terenkripsi
    baris_event = " ".join(
        str(vars(e)) + repr(e) for e in db_session.query(AiPenyediaEventModel).all()
    )
    log = " ".join(f"{r.getMessage()} {r.__dict__}" for r in tangkap.records)
    gabung = " ".join([baris_event, log, repr(rec), repr(st), st.model_dump_json(), repr(svc)])
    assert _KUNCI_API not in gabung and cipher not in gabung and induk not in gabung
    assert len(tangkap.records) == 3
    pesan = ""
    try:
        SqlAiPenyediaService(db_session, _settings("")).pasang_kredensial(
            _KUNCI_API, _ALASAN, _AKTOR
        )
    except KunciIndukTidakAda as exc:
        pesan = str(exc) + repr(exc)
    assert _KUNCI_API not in pesan


def test_tabel_ada_dan_kolom_kredensial_bukan_teks_asli(
    svc: SqlAiPenyediaService, db_session: Session
) -> None:
    svc.pasang_kredensial(_KUNCI_API, _ALASAN, _AKTOR)
    mentah = db_session.execute(
        text("select kredensial_terenkripsi from ai_penyedia_pengaturan")
    ).scalar_one()
    assert _KUNCI_API not in mentah
