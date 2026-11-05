"""Test gateway dan worker job AI: alur gerbang -> register -> model -> validasi -> karantina.

Klien model selalu tiruan; tidak ada jaringan dan tidak ada kunci API.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from anjab_abk_backend.ai import gateway as modul_gateway
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR, AiGateway, FungsiAi
from anjab_abk_backend.ai.guardrail import GUARDRAIL_V1, hash_instruksi, susun_instruksi
from anjab_abk_backend.ai.klien import (
    JawabanModel,
    KesalahanModelPermanen,
    KesalahanModelSementara,
    KunciModelTidakAda,
)
from anjab_abk_backend.ai.redaksi import SumberAi
from anjab_abk_backend.ai.worker import jalankan_satu, klaim_job, pulihkan_job_basi
from anjab_abk_backend.config import Settings
from anjab_abk_backend.errors import NotFoundError
from anjab_abk_backend.fitur import FiturNonaktifError
from anjab_abk_backend.models import AiRunModel, AsyncJobModel, _utcnow
from anjab_abk_backend.schemas.ai_run import StatusQaAi
from anjab_abk_backend.schemas.async_job import StatusJob
from anjab_abk_backend.schemas.common import FiturKode
from anjab_abk_backend.services.ai_run_sql import SqlAiRunService
from anjab_abk_backend.services.ai_saklar_sql import SqlSaklarAiService
from anjab_abk_backend.services.async_job_sql import SqlAsyncJobService

pytestmark = pytest.mark.usefixtures("penyedia_api")

_HIDUP = Settings(_env_file=None, feature_ai_narrative_draft=True)
_MATI = Settings(_env_file=None, feature_ai_narrative_draft=False)
_SAMARKAN = Settings(_env_file=None, feature_ai_narrative_draft=True, ai_pii_mode="SAMARKAN")

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


def _sumber(sid: str = "s1", teks: str = _TEKS, jenis: str = "SINTETIS") -> SumberAi:
    return SumberAi(source_id=sid, source_hash=_sha(teks), jenis=jenis, teks=teks)


def _keluaran(**ubah: Any) -> str:
    data: dict[str, Any] = {
        "status": "AI_DRAFT",
        "source_refs": [{"source_id": "s1", "source_hash": _sha(_TEKS)}],
        "cited_spans": [{"source_id": "s1", "span": "mengajar kelas lima"}],
        "confidence_reason": "Kutipan langsung.",
        "unknowns": [],
        "contradictions": [],
        "human_review_required": True,
        "isi": {"ringkas": "Guru mengajar."},
    }
    data.update(ubah)
    return json.dumps(data)


def _jawab(teks: str | None, stop: str = "end_turn") -> JawabanModel:
    return JawabanModel(
        teks=teks, model_dilayani="claude-tiruan", stop_reason=stop, input_tokens=7, output_tokens=3
    )


class KlienTiruan:
    """Klien model tiruan: mengembalikan/melempar respons berurutan dan mencatat panggilan."""

    def __init__(self, *respons: JawabanModel | Exception, sebelum: Any = None) -> None:
        self.respons = list(respons)
        self.panggilan: list[tuple[str, str, dict[str, Any]]] = []
        self._sebelum = sebelum

    def panggil(self, instruksi: str, masukan_json: str, skema: dict[str, Any]) -> JawabanModel:
        self.panggilan.append((instruksi, masukan_json, skema))
        if self._sebelum is not None:
            self._sebelum()
        r = self.respons.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class Pabrik:
    """Pembuat klien yang menghitung berapa kali klien dibuat."""

    def __init__(self, klien: KlienTiruan) -> None:
        self.klien = klien
        self.dibuat = 0

    def __call__(self) -> KlienTiruan:
        self.dibuat += 1
        return self.klien


@pytest.fixture
def fab(db_session: Session):
    @contextmanager
    def _fab() -> Iterator[Session]:
        yield db_session

    return _fab


def _ajukan(db: Session, sumber: list[SumberAi] | None = None, settings: Settings = _HIDUP):
    return AiGateway(db, settings, registri=_REG).ajukan(
        _FUNGSI.kode,
        [_sumber()] if sumber is None else sumber,
        {"topik": "umum"},
        "obj-1",
        "tester",
    )


def _run(db: Session, job_id: str) -> AiRunModel:
    job = db.get(AsyncJobModel, job_id)
    run = db.get(AiRunModel, job.ref_id)
    db.refresh(run)
    return run


def _proses(db: Session, fab, klien: KlienTiruan, settings: Settings = _HIDUP) -> str | None:
    return jalankan_satu(fab, settings, Pabrik(klien), _REG)


def test_alur_lolos_run_lolos_job_succeeded_masukan_kosong(db_session: Session, fab) -> None:
    job = _ajukan(db_session)
    assert job.status == StatusJob.PENDING and job.jenis == _FUNGSI.kode
    run = _run(db_session, job.id)
    assert run.status_qa == "MENUNGGU" and run.masukan["sumber"][0]["teks"] == _TEKS
    assert run.prompt_version == "guardrail-1+v1"
    assert run.prompt_hash == hash_instruksi(_FUNGSI.instruksi)

    klien = KlienTiruan(_jawab(_keluaran()))
    assert _proses(db_session, fab, klien) == job.id
    db_session.refresh(db_session.get(AsyncJobModel, job.id))
    akhir = SqlAsyncJobService(db_session, _HIDUP).get(job.id)
    run = _run(db_session, job.id)
    assert akhir.status == StatusJob.SUCCEEDED
    assert run.status_qa == "LOLOS" and run.masukan is None
    assert run.keluaran["status"] == "AI_DRAFT"
    assert (run.input_tokens, run.output_tokens, run.model_dilayani) == (7, 3, "claude-tiruan")


def test_flag_mati_ajukan_409_tanpa_baris_dan_klien_tak_dibuat(db_session: Session, fab) -> None:
    pabrik = Pabrik(KlienTiruan())
    with pytest.raises(FiturNonaktifError):
        _ajukan(db_session, settings=_MATI)
    assert db_session.query(AiRunModel).count() == 0
    assert db_session.query(AsyncJobModel).count() == 0
    assert jalankan_satu(fab, _MATI, pabrik, _REG) is None
    assert pabrik.dibuat == 0


def test_saklar_mati_sebelum_klaim_ajukan_ditolak_worker_tak_klaim(
    db_session: Session, fab
) -> None:
    job = _ajukan(db_session)
    SqlSaklarAiService(db_session, _HIDUP).matikan(FiturKode.AI_NARRATIVE_DRAFT, "uji saklar", "t")
    with pytest.raises(FiturNonaktifError):
        _ajukan(db_session)
    pabrik = Pabrik(KlienTiruan())
    assert jalankan_satu(fab, _HIDUP, pabrik, _REG) is None
    assert pabrik.dibuat == 0
    assert SqlAsyncJobService(db_session, _HIDUP).get(job.id).status == StatusJob.PENDING


def test_saklar_mati_selama_panggilan_karantina(db_session: Session, fab) -> None:
    job = _ajukan(db_session)

    def matikan() -> None:
        SqlSaklarAiService(db_session, _HIDUP).matikan(
            FiturKode.AI_NARRATIVE_DRAFT, "mati saat panggilan", "t"
        )

    _proses(db_session, fab, KlienTiruan(_jawab(_keluaran()), sebelum=matikan))
    run = _run(db_session, job.id)
    assert run.status_qa == "KARANTINA" and run.kode_qa == ["SAKLAR_DIMATIKAN"]
    assert run.keluaran is None
    assert SqlAsyncJobService(db_session, _HIDUP).get(job.id).status == StatusJob.MANUAL_REVIEW


@pytest.mark.parametrize(
    "sumber",
    [
        [],
        [SumberAi(source_id="s1", source_hash="", jenis="SINTETIS", teks=_TEKS)],
        [SumberAi(source_id="", source_hash=_sha(_TEKS), jenis="SINTETIS", teks=_TEKS)],
    ],
    ids=["kosong", "hash-hilang", "id-hilang"],
)
def test_sumber_kosong_atau_metadata_hilang_evidence_gap_tanpa_model(
    db_session: Session, fab, sumber: list[SumberAi]
) -> None:
    job = _ajukan(db_session, sumber)
    assert job.status == StatusJob.MANUAL_REVIEW
    run = _run(db_session, job.id)
    assert run.status_qa == "EVIDENCE_GAP"
    assert run.kode_qa == ["SUMBER_KOSONG" if not sumber else "METADATA_SUMBER_HILANG"]
    pabrik = Pabrik(KlienTiruan())
    assert jalankan_satu(fab, _HIDUP, pabrik, _REG) is None
    assert pabrik.dibuat == 0


def test_pii_pada_masukan_diblokir_klien_tak_dipanggil(db_session: Session, fab) -> None:
    job = _ajukan(db_session, [_sumber(teks="Hubungi guru@sekolah.id untuk jadwal.")])
    run = _run(db_session, job.id)
    assert run.status_qa == "DIBLOKIR" and run.kode_qa == ["PII_DITEMUKAN"]
    assert job.status == StatusJob.MANUAL_REVIEW and run.masukan is None
    pabrik = Pabrik(KlienTiruan())
    assert jalankan_satu(fab, _HIDUP, pabrik, _REG) is None and pabrik.dibuat == 0


def test_jenis_ditolak_dan_urutan_alasan_pertama_fail_closed(db_session: Session) -> None:
    job = _ajukan(
        db_session,
        [_sumber("a"), _sumber("b", jenis="WCP"), _sumber("c", teks="surel x@y.id")],
    )
    run = _run(db_session, job.id)
    assert run.status_qa == "DIBLOKIR" and run.kode_qa == ["JENIS_DITOLAK"]
    assert [s["source_id"] for s in run.sumber] == ["a", "b", "c"]


def test_masukan_ke_klien_hanya_teks_tersamarkan_dan_teks_di_pesan_user(
    db_session: Session, fab
) -> None:
    asli = "Kontak resmi guru@sekolah.id mengajar kelas lima."
    job = _ajukan(db_session, [_sumber(teks=asli)], _SAMARKAN)
    klien = KlienTiruan(
        _jawab(_keluaran(source_refs=[{"source_id": "s1", "source_hash": _sha(asli)}]))
    )
    _proses(db_session, fab, klien, _SAMARKAN)
    instruksi, masukan_json, _ = klien.panggilan[0]
    assert "guru@sekolah.id" not in masukan_json and "[EMAIL_1]" in masukan_json
    assert instruksi == susun_instruksi(_FUNGSI.instruksi) and instruksi.startswith(GUARDRAIL_V1)
    assert "mengajar kelas lima" in masukan_json and "mengajar kelas lima" not in instruksi
    assert "ref_id" not in json.loads(masukan_json)
    assert _run(db_session, job.id).status_qa == "LOLOS"


def test_pii_pada_keluaran_karantina(db_session: Session, fab) -> None:
    job = _ajukan(db_session)
    _proses(db_session, fab, KlienTiruan(_jawab(_keluaran(isi={"ringkas": "kirim ke a@b.id"}))))
    run = _run(db_session, job.id)
    assert run.status_qa == "KARANTINA" and run.kode_qa == ["PII_KELUARAN"] and run.keluaran is None
    assert SqlAsyncJobService(db_session, _HIDUP).get(job.id).status == StatusJob.MANUAL_REVIEW


def test_sumber_karangan_karantina(db_session: Session, fab) -> None:
    job = _ajukan(db_session)
    palsu = _keluaran(
        source_refs=[{"source_id": "karangan", "source_hash": _sha("x")}],
        cited_spans=[{"source_id": "karangan", "span": "apa saja"}],
    )
    _proses(db_session, fab, KlienTiruan(_jawab(palsu)))
    run = _run(db_session, job.id)
    assert run.status_qa == "KARANTINA" and "SUMBER_FIKTIF" in run.kode_qa
    assert SqlAsyncJobService(db_session, _HIDUP).get(job.id).status == StatusJob.MANUAL_REVIEW


def test_evidence_gap_dari_model_manual_review(db_session: Session, fab) -> None:
    job = _ajukan(db_session)
    gap = _keluaran(status="EVIDENCE_GAP", cited_spans=[], unknowns=["data tidak cukup"])
    _proses(db_session, fab, KlienTiruan(_jawab(gap)))
    assert _run(db_session, job.id).status_qa == "EVIDENCE_GAP"
    assert SqlAsyncJobService(db_session, _HIDUP).get(job.id).status == StatusJob.MANUAL_REVIEW


@pytest.mark.parametrize(
    ("stop", "kode"), [("refusal", "MODEL_MENOLAK"), ("max_tokens", "KELUARAN_TERPOTONG")]
)
def test_refusal_dan_max_tokens_manual_review(
    db_session: Session, fab, stop: str, kode: str
) -> None:
    job = _ajukan(db_session)
    teks = None if stop == "refusal" else '{"terpotong'
    _proses(db_session, fab, KlienTiruan(_jawab(teks, stop)))
    run = _run(db_session, job.id)
    assert run.status_qa == "KARANTINA" and run.kode_qa == [kode] and run.stop_reason == stop
    assert SqlAsyncJobService(db_session, _HIDUP).get(job.id).status == StatusJob.MANUAL_REVIEW


def test_galat_sementara_retry_sampai_batas_lalu_manual_review(db_session: Session, fab) -> None:
    job = _ajukan(db_session)
    klien = KlienTiruan(*[KesalahanModelSementara("x") for _ in range(3)])
    svc = SqlAsyncJobService(db_session, _HIDUP)
    _proses(db_session, fab, klien)
    antara = svc.get(job.id)
    assert antara.status == StatusJob.PENDING and antara.percobaan == 1
    assert _run(db_session, job.id).status_qa == "MENUNGGU"
    _proses(db_session, fab, klien)
    assert svc.get(job.id).percobaan == 2
    _proses(db_session, fab, klien)
    akhir = svc.get(job.id)
    assert akhir.status == StatusJob.MANUAL_REVIEW and len(klien.panggilan) == 3
    assert _run(db_session, job.id).status_qa == "GAGAL"


@pytest.mark.parametrize(
    ("galat", "kode"),
    [
        (KesalahanModelPermanen("x"), "MODEL_PERMANEN"),
        (KunciModelTidakAda("x"), "KUNCI_MODEL_TIDAK_ADA"),
    ],
)
def test_galat_permanen_dan_kunci_hilang_gagal_manual_review(
    db_session: Session, fab, galat: Exception, kode: str
) -> None:
    job = _ajukan(db_session)
    _proses(db_session, fab, KlienTiruan(galat))
    assert _run(db_session, job.id).status_qa == "GAGAL"
    akhir = SqlAsyncJobService(db_session, _HIDUP).get(job.id)
    assert akhir.status == StatusJob.MANUAL_REVIEW and akhir.error_code == kode


def test_fungsi_tak_terdaftar_404_tanpa_baris(db_session: Session) -> None:
    with pytest.raises(NotFoundError):
        AiGateway(db_session, _HIDUP).ajukan("tidak_ada", [_sumber()], {}, None, None)
    assert db_session.query(AsyncJobModel).count() == 0


def test_satu_siklus_hanya_menulis_ai_run_dan_async_job(db_session: Session, fab) -> None:
    ditulis: set[str] = set()

    def _catat(session: Session, _ctx: Any, _inst: Any) -> None:
        for obj in (*session.new, *session.dirty, *session.deleted):
            ditulis.add(type(obj).__name__)

    event.listen(db_session, "before_flush", _catat)
    try:
        _ajukan(db_session)
        _proses(db_session, fab, KlienTiruan(_jawab(_keluaran())))
        _ajukan(db_session, [])
    finally:
        event.remove(db_session, "before_flush", _catat)
    assert ditulis == {"AiRunModel", "AsyncJobModel"}


def test_job_running_basi_menjadi_failed_worker_terhenti(db_session: Session) -> None:
    svc = SqlAsyncJobService(db_session, _HIDUP)
    basi = svc.create(FiturKode.AI_NARRATIVE_DRAFT, "uji_ringkas", None, None)
    segar = svc.create(FiturKode.AI_NARRATIVE_DRAFT, "uji_ringkas", None, None)
    for j in (basi, segar):
        svc.transisi(j.id, StatusJob.RUNNING)
    rec = db_session.get(AsyncJobModel, basi.id)
    rec.updated_at = _utcnow() - timedelta(seconds=_HIDUP.ai_timeout_detik * 2 + 60)
    db_session.flush()
    assert pulihkan_job_basi(db_session, _HIDUP) == 1
    assert svc.get(basi.id).status == StatusJob.FAILED
    assert svc.get(basi.id).error_code == "WORKER_TERHENTI"
    assert svc.get(segar.id).status == StatusJob.RUNNING


def test_dua_klaim_bersamaan_tidak_mengambil_job_yang_sama(engine) -> None:
    s0, s1, s2 = Session(engine), Session(engine), Session(engine)
    ids: list[str] = []
    try:
        svc = SqlAsyncJobService(s0, _HIDUP)
        ids = [svc.create(FiturKode.AI_NARRATIVE_DRAFT, "uji", None, None).id for _ in range(2)]
        s0.commit()
        a = klaim_job(s1, _HIDUP)  # transaksi s1 terbuka: baris terkunci
        b = klaim_job(s2, _HIDUP)  # SKIP LOCKED: harus mengambil baris lain
        c = klaim_job(Session(engine), _HIDUP)  # keduanya terkunci: tidak ada
        assert a is not None and b is not None and a.id != b.id
        assert {a.id, b.id} == set(ids) and c is None
    finally:
        for s in (s1, s2):
            s.rollback()
            s.close()
        s0.query(AsyncJobModel).filter(AsyncJobModel.id.in_(ids)).delete()
        s0.commit()
        s0.close()


def test_registri_produksi_kosong_dan_rute_pengaju_hanya_di_kasus_narasi(app) -> None:
    """Pengganti uji #90 "OpenAPI tidak memuat rute pengaju" (diganti oleh #98).

    Rute pengaju kini ada, tetapi hanya satu: ``POST /narasi/kasus/{id}/draf-ai``. Perilaku
    flag mati (409 tanpa baris) diuji di ``test_narasi_draf_ai.py``.
    """
    assert FUNGSI_TERDAFTAR == {} and modul_gateway.FUNGSI_TERDAFTAR is FUNGSI_TERDAFTAR
    with TestClient(app) as c:
        paths = c.get("/openapi.json").json()["paths"]
    pengaju = [p for p, ops in paths.items() if "post" in ops and p.endswith("/draf-ai")]
    assert pengaju == ["/api/v1/narasi/kasus/{narasi_id}/draf-ai"]
    assert not [p for p in paths if "ajukan" in p or "/ai/jobs" in p or "/ai/job" in p]
    assert not [p for p in paths if p.endswith("/ai") or "/ai/ajukan" in p]


def test_tutup_run_hanya_lewat_service_register(db_session: Session) -> None:
    job = _ajukan(db_session)
    run = SqlAiRunService(db_session, _HIDUP).get(job.ref_id)
    assert run.status_qa == StatusQaAi.MENUNGGU
