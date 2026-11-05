"""Test pabrik klien model dan pengalihan gateway/worker ke pengaturan penyedia (#111).

Seluruh kunci sintetis; klien SDK diganti transport tiruan; tidak ada jaringan.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import anthropic
import httpx2
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy.orm import Session

from anjab_abk_backend.ai import penyedia as modul_penyedia
from anjab_abk_backend.ai.gateway import AiGateway, FungsiAi
from anjab_abk_backend.ai.klien import AnthropicKlienModel, JawabanModel, KunciModelTidakAda
from anjab_abk_backend.ai.penyedia import (
    AiPenyediaMode,
    KlienTerpilih,
    PenyediaMati,
    PenyediaTidakTersedia,
    buat_klien_model,
)
from anjab_abk_backend.ai.redaksi import SumberAi
from anjab_abk_backend.ai.worker import jalankan_satu
from anjab_abk_backend.config import Settings
from anjab_abk_backend.fitur import FiturNonaktifError
from anjab_abk_backend.models import (
    AiPenyediaPengaturanModel,
    AiRunModel,
    AsyncJobModel,
)
from anjab_abk_backend.schemas.ai_run import StatusQaAi
from anjab_abk_backend.schemas.async_job import StatusJob
from anjab_abk_backend.services.ai_penyedia_sql import SqlAiPenyediaService
from anjab_abk_backend.services.ai_run_sql import SqlAiRunService

_INDUK = SecretStr(Fernet.generate_key().decode())
_CFG = Settings(_env_file=None, feature_ai_narrative_draft=True, ai_kredensial_kunci_induk=_INDUK)
_KUNCI_1 = "kunci-sintetis-satu-AAAA1111"
_KUNCI_2 = "kunci-sintetis-dua-BBBB2222"
_ALASAN = "Alasan uji pabrik"
_AKTOR = "admin@example.test"
_TEKS = "Guru mengajar kelas lima setiap hari."
_FUNGSI = FungsiAi(
    kode="uji_ringkas",
    prompt_version="v1",
    instruksi="Ringkas sumber.",
    skema_isi={
        "type": "object",
        "additionalProperties": False,
        "required": ["ringkas"],
        "properties": {"ringkas": {"type": "string"}},
    },
)
_REG = {_FUNGSI.kode: _FUNGSI}


def _sha(teks: str) -> str:
    return hashlib.sha256(teks.encode("utf-8")).hexdigest()


def _sumber(jenis: str = "SINTETIS", teks: str = _TEKS) -> SumberAi:
    return SumberAi(source_id="s1", source_hash=_sha(teks), jenis=jenis, teks=teks)


def _keluaran() -> str:
    return json.dumps(
        {
            "status": "AI_DRAFT",
            "source_refs": [{"source_id": "s1", "source_hash": _sha(_TEKS)}],
            "cited_spans": [{"source_id": "s1", "span": "mengajar kelas lima"}],
            "confidence_reason": "Kutipan langsung.",
            "unknowns": [],
            "contradictions": [],
            "human_review_required": True,
            "isi": {"ringkas": "Guru mengajar."},
        }
    )


def _jawab() -> JawabanModel:
    return JawabanModel(
        teks=_keluaran(),
        model_dilayani="claude-tiruan",
        stop_reason="end_turn",
        input_tokens=7,
        output_tokens=3,
    )


@pytest.fixture
def fab(db_session: Session):
    @contextmanager
    def _fab() -> Iterator[Session]:
        yield db_session

    return _fab


def _svc(db: Session, settings: Settings = _CFG) -> SqlAiPenyediaService:
    return SqlAiPenyediaService(db, settings)


def _atur_mode(db: Session, mode: AiPenyediaMode) -> None:
    """Set mode langsung pada baris tunggal (membuatnya bila belum ada)."""
    rec = db.get(AiPenyediaPengaturanModel, "TUNGGAL")
    if rec is None:
        db.add(AiPenyediaPengaturanModel(id="TUNGGAL", mode=mode.value, diperbarui_oleh="uji"))
    else:
        rec.mode = mode.value
    db.flush()


def _ajukan(db: Session, settings: Settings = _CFG, sumber: list[SumberAi] | None = None):
    return AiGateway(db, settings, registri=_REG).ajukan(
        _FUNGSI.kode, [_sumber()] if sumber is None else sumber, {"topik": "umum"}, "obj-1", "t"
    )


def _run(db: Session, job_id: str) -> AiRunModel:
    job = db.get(AsyncJobModel, job_id)
    run = db.get(AiRunModel, job.ref_id)
    db.refresh(run)
    return run


class _Rekam(AnthropicKlienModel):
    """Klien nyata (pemeriksaan kunci kosong tetap berlaku) yang mencatat argumen dan menjawab."""

    catatan: list[tuple[str | None, str, str]] = []
    panggilan = 0

    def __init__(self, settings: Settings, *, kunci_api: str | None, model: str, effort: str, **kw):
        super().__init__(settings, kunci_api=kunci_api, model=model, effort=effort, **kw)
        _Rekam.catatan.append((kunci_api, model, effort))

    def panggil(self, instruksi: str, masukan_json: str, skema: dict[str, Any]) -> JawabanModel:
        _Rekam.panggilan += 1
        return _jawab()


@pytest.fixture
def rekam(monkeypatch: pytest.MonkeyPatch):
    _Rekam.catatan = []
    _Rekam.panggilan = 0
    monkeypatch.setattr(modul_penyedia, "AnthropicKlienModel", _Rekam)
    return _Rekam


@pytest.fixture
def sdk_dilarang(monkeypatch: pytest.MonkeyPatch):
    """Konstruksi klien SDK menggagalkan tes (bukti nol panggilan/nol klien)."""

    def _larang(**_k: Any) -> None:
        raise AssertionError("klien SDK tidak boleh dibuat")

    monkeypatch.setattr(anthropic, "Anthropic", _larang)


# --- pabrik ------------------------------------------------------------------------------


def test_pabrik_mode_mati_tanpa_baris(db_session: Session) -> None:
    with pytest.raises(PenyediaMati):
        buat_klien_model(db_session, _CFG)


def test_pabrik_mode_mati_eksplisit(db_session: Session) -> None:
    _atur_mode(db_session, AiPenyediaMode.MATI)
    with pytest.raises(PenyediaMati):
        buat_klien_model(db_session, _CFG)


def test_pabrik_langganan_tidak_tersedia(db_session: Session) -> None:
    _atur_mode(db_session, AiPenyediaMode.LANGGANAN_CLAUDE)
    with pytest.raises(PenyediaTidakTersedia):
        buat_klien_model(db_session, _CFG)


def test_pabrik_kunci_kosong_env_terisi_diabaikan(
    db_session: Session, monkeypatch: pytest.MonkeyPatch, sdk_dilarang: None
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "kunci-env-sintetis")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "token-env-sintetis")
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    with pytest.raises(KunciModelTidakAda):
        buat_klien_model(db_session, _CFG)


def test_pabrik_ciphertext_rusak_kunci_tidak_ada(db_session: Session, sdk_dilarang: None) -> None:
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    rec = db_session.get(AiPenyediaPengaturanModel, "TUNGGAL")
    rec.kredensial_terenkripsi = "bukan-token-fernet"
    rec.kredensial_akhiran = "xxxx"
    db_session.flush()
    with pytest.raises(KunciModelTidakAda):
        buat_klien_model(db_session, _CFG)


def test_pabrik_kunci_induk_hilang_kunci_tidak_ada(db_session: Session, sdk_dilarang: None) -> None:
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    _svc(db_session).pasang_kredensial(_KUNCI_1, _ALASAN, _AKTOR)
    tanpa_induk = Settings(_env_file=None)
    with pytest.raises(KunciModelTidakAda):
        buat_klien_model(db_session, tanpa_induk)


def test_pabrik_api_meneruskan_kunci_model_effort_dan_repr_aman(
    db_session: Session, rekam: type[_Rekam]
) -> None:
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    s = _svc(db_session)
    s.pasang_kredensial(_KUNCI_1, _ALASAN, _AKTOR)
    s.ubah_model("claude-sonnet-5-5", "low", _ALASAN, _AKTOR)
    t = buat_klien_model(db_session, _CFG)
    assert isinstance(t, KlienTerpilih)
    assert rekam.catatan == [(_KUNCI_1, "claude-sonnet-5-5", "low")]
    assert (t.mode, t.model, t.effort) == (AiPenyediaMode.API_ANTHROPIC, "claude-sonnet-5-5", "low")
    for teks in (repr(t), str(t), repr(t.klien)):
        assert _KUNCI_1 not in teks and "kunci-sintetis" not in teks


def test_repr_klien_asli_tidak_memuat_kunci() -> None:
    k = AnthropicKlienModel(_CFG, kunci_api=_KUNCI_2, model="m", effort="low")
    assert _KUNCI_2 not in repr(k) and _KUNCI_2 not in str(k)


# --- gateway -----------------------------------------------------------------------------


def test_gateway_mode_mati_menolak_tanpa_baris(db_session: Session) -> None:
    _atur_mode(db_session, AiPenyediaMode.MATI)
    with pytest.raises(FiturNonaktifError):
        _ajukan(db_session)
    assert db_session.query(AiRunModel).count() == 0
    assert db_session.query(AsyncJobModel).count() == 0


def test_gateway_tanpa_baris_pengaturan_dibaca_mati(db_session: Session) -> None:
    with pytest.raises(FiturNonaktifError):
        _ajukan(db_session)
    assert db_session.query(AiRunModel).count() == 0


@pytest.mark.parametrize("mode", [AiPenyediaMode.API_ANTHROPIC, AiPenyediaMode.LANGGANAN_CLAUDE])
@pytest.mark.parametrize(
    ("jenis", "teks", "env", "status_job", "kode"),
    [
        ("SINTETIS", _TEKS, ["SINTETIS"], StatusJob.PENDING, []),
        ("DOKUMEN_RESMI", _TEKS, ["SINTETIS"], StatusJob.MANUAL_REVIEW, ["JENIS_DITOLAK"]),
        ("WCP_X", _TEKS, ["SINTETIS", "WCP_X"], StatusJob.MANUAL_REVIEW, ["JENIS_DITOLAK"]),
        (
            "SINTETIS",
            "Hubungi guru@sekolah.id untuk jadwal.",
            ["SINTETIS"],
            StatusJob.MANUAL_REVIEW,
            ["PII_DITEMUKAN"],
        ),
        ("DOKUMEN_RESMI", _TEKS, ["SINTETIS", "DOKUMEN_RESMI"], StatusJob.PENDING, []),
    ],
    ids=["sintetis", "dokumen-di-luar-env", "wcp-di-env", "pii", "dokumen-diizinkan-env"],
)
def test_gateway_gerbang_data_sama_untuk_kedua_mode(
    db_session: Session,
    mode: AiPenyediaMode,
    jenis: str,
    teks: str,
    env: list[str],
    status_job: StatusJob,
    kode: list[str],
) -> None:
    _atur_mode(db_session, mode)
    cfg = Settings(_env_file=None, feature_ai_narrative_draft=True, ai_jenis_sumber_diizinkan=env)
    job = _ajukan(db_session, cfg, [_sumber(jenis, teks)])
    run = _run(db_session, job.id)
    assert job.status == status_job
    assert run.kode_qa == kode
    assert run.penyedia == mode.value  # juga pada run yang ditolak gerbang
    assert run.status_qa == ("MENUNGGU" if not kode else "DIBLOKIR")


def test_gateway_model_dari_pengaturan_bukan_settings(db_session: Session) -> None:
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    _svc(db_session).ubah_model("claude-haiku-5", "medium", _ALASAN, _AKTOR)
    job = _ajukan(db_session)
    assert _run(db_session, job.id).model_diminta == "claude-haiku-5"


def test_penyedia_tampil_di_rincian_register_run(client_as, db_session: Session) -> None:
    _atur_mode(db_session, AiPenyediaMode.LANGGANAN_CLAUDE)
    job = _ajukan(db_session)
    admin = client_as("admin-uji", groups=["admin"])
    r = admin.get(f"/api/v1/system/ai/runs/{job.ref_id}")
    assert r.status_code == 200 and r.json()["penyedia"] == "LANGGANAN_CLAUDE"
    daftar = admin.get("/api/v1/system/ai/runs").json()["items"]
    assert [x["penyedia"] for x in daftar if x["id"] == job.ref_id] == ["LANGGANAN_CLAUDE"]


# --- worker ------------------------------------------------------------------------------


def test_worker_dua_job_kunci_dan_model_berbeda_tanpa_restart(
    db_session: Session, fab, rekam: type[_Rekam]
) -> None:
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    s = _svc(db_session)
    s.pasang_kredensial(_KUNCI_1, _ALASAN, _AKTOR)
    s.ubah_model("claude-opus-5-4", "medium", _ALASAN, _AKTOR)
    j1 = _ajukan(db_session)
    assert jalankan_satu(fab, _CFG, None, _REG) == j1.id
    s.pasang_kredensial(_KUNCI_2, _ALASAN, _AKTOR)
    s.ubah_model("claude-sonnet-5-5", "low", _ALASAN, _AKTOR)
    j2 = _ajukan(db_session)
    assert jalankan_satu(fab, _CFG, None, _REG) == j2.id
    assert rekam.catatan == [
        (_KUNCI_1, "claude-opus-5-4", "medium"),
        (_KUNCI_2, "claude-sonnet-5-5", "low"),
    ]
    assert _run(db_session, j1.id).status_qa == "LOLOS"
    assert _run(db_session, j2.id).penyedia == "API_ANTHROPIC"


def test_worker_mode_mati_gagal_penyedia_mati_nol_panggilan(
    db_session: Session, fab, rekam: type[_Rekam], sdk_dilarang: None
) -> None:
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    job = _ajukan(db_session)
    _atur_mode(db_session, AiPenyediaMode.MATI)
    assert jalankan_satu(fab, _CFG, None, _REG) == job.id
    run = _run(db_session, job.id)
    assert (run.status_qa, run.kode_qa, run.penyedia) == ("GAGAL", ["PENYEDIA_MATI"], "MATI")
    akhir = db_session.get(AsyncJobModel, job.id)
    assert akhir.status == StatusJob.MANUAL_REVIEW.value and akhir.error_code == "PENYEDIA_MATI"
    assert rekam.panggilan == 0 and rekam.catatan == []


def test_worker_mati_juga_berlaku_untuk_pembuat_klien_uji(db_session: Session, fab) -> None:
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    job = _ajukan(db_session)
    _atur_mode(db_session, AiPenyediaMode.MATI)
    dibuat: list[int] = []
    assert jalankan_satu(fab, _CFG, lambda: dibuat.append(1), _REG) == job.id  # type: ignore[arg-type,return-value]
    assert dibuat == [] and _run(db_session, job.id).kode_qa == ["PENYEDIA_MATI"]


def test_worker_mode_diubah_antara_pengajuan_dan_panggilan_mencatat_mode_saat_panggilan(
    db_session: Session, fab, sdk_dilarang: None
) -> None:
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    job = _ajukan(db_session)
    assert _run(db_session, job.id).penyedia == "API_ANTHROPIC"
    _svc(db_session).ubah_mode(AiPenyediaMode.LANGGANAN_CLAUDE, _ALASAN, _AKTOR)
    jalankan_satu(fab, _CFG, None, _REG)
    run = _run(db_session, job.id)
    assert run.penyedia == "LANGGANAN_CLAUDE"
    assert (run.status_qa, run.kode_qa) == ("GAGAL", ["PENYEDIA_TIDAK_TERSEDIA"])
    akhir = db_session.get(AsyncJobModel, job.id)
    assert akhir.status == StatusJob.MANUAL_REVIEW.value
    assert akhir.error_code == "PENYEDIA_TIDAK_TERSEDIA"


def test_worker_penyedia_dicatat_sebelum_panggilan_dengan_klien_uji(
    db_session: Session, fab
) -> None:
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    job = _ajukan(db_session)
    _svc(db_session).ubah_mode(AiPenyediaMode.LANGGANAN_CLAUDE, _ALASAN, _AKTOR)
    nilai: list[str | None] = []

    class _K:
        def panggil(self, *_a: Any) -> JawabanModel:
            nilai.append(_run(db_session, job.id).penyedia)
            return _jawab()

    jalankan_satu(fab, _CFG, _K, _REG)  # type: ignore[arg-type]
    assert nilai == ["LANGGANAN_CLAUDE"]


def test_run_final_tidak_tertimpa_catat_penyedia(db_session: Session) -> None:
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    job = _ajukan(db_session)
    runs = SqlAiRunService(db_session, _CFG)
    runs.tutup(job.ref_id, StatusQaAi.LOLOS, [], {"x": 1}, "end_turn", "m", 1, 1)
    assert runs.catat_penyedia(job.ref_id, "LANGGANAN_CLAUDE") is False
    assert _run(db_session, job.id).penyedia == "API_ANTHROPIC"
    assert runs.catat_penyedia("tidak-ada", "MATI") is False


def test_worker_kunci_kosong_env_terisi_kunci_model_tidak_ada_nol_panggilan(
    db_session: Session, fab, monkeypatch: pytest.MonkeyPatch, sdk_dilarang: None
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "kunci-env-sintetis")
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    job = _ajukan(db_session)
    jalankan_satu(fab, _CFG, None, _REG)
    run = _run(db_session, job.id)
    assert (run.status_qa, run.kode_qa) == ("GAGAL", ["KUNCI_MODEL_TIDAK_ADA"])
    assert db_session.get(AsyncJobModel, job.id).error_code == "KUNCI_MODEL_TIDAK_ADA"


def _transport_401(kunci: str):
    def _h(_req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            401, json={"type": "error", "error": {"type": "authentication_error", "message": kunci}}
        )

    return _h


def _semua_teks(db: Session, job_id: str) -> str:
    run = _run(db, job_id)
    job = db.get(AsyncJobModel, job_id)
    kolom = {c.name: getattr(run, c.name) for c in AiRunModel.__table__.columns}
    kolom |= {c.name: getattr(job, c.name) for c in AsyncJobModel.__table__.columns}
    return json.dumps(kolom, default=str)


def test_galat_permanen_kunci_tidak_bocor_ke_log_run_job_maupun_pesan(
    db_session: Session, fab, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    asli = anthropic.Anthropic

    def _buat(**kw: Any):
        return asli(
            **kw,
            http_client=httpx2.Client(transport=httpx2.MockTransport(_transport_401(_KUNCI_1))),
        )

    monkeypatch.setattr(anthropic, "Anthropic", _buat)
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    _svc(db_session).pasang_kredensial(_KUNCI_1, _ALASAN, _AKTOR)
    job = _ajukan(db_session)
    caplog.set_level(logging.DEBUG)
    jalankan_satu(fab, _CFG, None, _REG)
    run = _run(db_session, job.id)
    assert (run.status_qa, run.kode_qa) == ("GAGAL", ["MODEL_PERMANEN"])
    assert _KUNCI_1 not in caplog.text
    assert _KUNCI_1 not in _semua_teks(db_session, job.id)
    assert _KUNCI_1[-4:] not in run.kode_qa[0]


def test_galat_dekripsi_kunci_tidak_bocor(
    db_session: Session, fab, caplog: pytest.LogCaptureFixture, sdk_dilarang: None
) -> None:
    _atur_mode(db_session, AiPenyediaMode.API_ANTHROPIC)
    _svc(db_session).pasang_kredensial(_KUNCI_1, _ALASAN, _AKTOR)
    rec = db_session.get(AiPenyediaPengaturanModel, "TUNGGAL")
    cipher = rec.kredensial_terenkripsi
    job = _ajukan(db_session)
    lain = Settings(
        _env_file=None,
        feature_ai_narrative_draft=True,
        ai_kredensial_kunci_induk=SecretStr(Fernet.generate_key().decode()),
    )
    caplog.set_level(logging.DEBUG)
    jalankan_satu(fab, lain, None, _REG)
    assert _run(db_session, job.id).kode_qa == ["KUNCI_MODEL_TIDAK_ADA"]
    teks = caplog.text + _semua_teks(db_session, job.id)
    assert _KUNCI_1 not in teks and cipher not in teks


# --- pemanggil baca_kunci_api ------------------------------------------------------------


def test_baca_kunci_api_hanya_dipanggil_pabrik() -> None:
    akar = Path(__file__).resolve().parent.parent / "src" / "anjab_abk_backend"
    pemanggil = {
        str(p.relative_to(akar))
        for p in akar.rglob("*.py")
        if ".baca_kunci_api(" in p.read_text(encoding="utf-8")
    }
    assert pemanggil == {"ai/penyedia.py"}


# --- konfigurasi lama diabaikan ----------------------------------------------------------


def test_field_ai_model_dan_effort_dihapus_dari_settings() -> None:
    assert "ai_model" not in Settings.model_fields and "ai_effort" not in Settings.model_fields


def test_env_proses_lama_diabaikan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_MODEL", "claude-lama")
    monkeypatch.setenv("AI_EFFORT", "max")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "kunci-env-sintetis")
    s = Settings(_env_file=None)
    assert not hasattr(s, "ai_model") and not hasattr(s, "ai_effort")


def test_berkas_env_lama_tidak_menggagalkan_start(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "AI_MODEL=claude-lama\nAI_EFFORT=max\nANTHROPIC_API_KEY=kunci-env-sintetis\n"
        "AI_MAX_TOKENS=123\n",
        encoding="utf-8",
    )
    s = Settings(_env_file=str(env))
    assert s.ai_max_tokens == 123


def test_berkas_env_tetap_menolak_nilai_salah_pada_field_dikenal(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("AI_MAX_TOKENS=bukan-angka\n", encoding="utf-8")
    with pytest.raises(ValueError):
        Settings(_env_file=str(env))
