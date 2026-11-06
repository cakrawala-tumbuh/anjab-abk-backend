"""Tes rute `POST /api/v1/narasi/sumber/{id}/ekstraksi-ai` (P01): hanya usulan, sumber tetap.

Klien model sungguhan tidak pernah dibuat; data sintetis; tanpa jaringan. Hasil ekstraksi hanya
boleh mendarat di `ai_usulan` (plus `ai_run` dan `async_job`), tidak di tabel `narasi_*` dan
tidak mengubah baris `narasi_sumber`.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from anjab_abk_backend.ai import klien as modul_klien
from anjab_abk_backend.ai.fungsi_p01 import FUNGSI_P01
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.klien import JawabanModel
from anjab_abk_backend.ai.penyerap_usulan import serap_usulan
from anjab_abk_backend.ai.worker import jalankan_satu
from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.models import (
    AiRunModel,
    AiUsulanModel,
    AsyncJobModel,
    NarasiAiPermintaanModel,
    NarasiEventModel,
    NarasiKasusModel,
    NarasiSumberModel,
    NarasiVersiModel,
    NarasiVersiSumberModel,
)
from anjab_abk_backend.narasi import penyerap
from anjab_abk_backend.schemas.ai_run import StatusQaAi
from anjab_abk_backend.schemas.ai_usulan import HasilSerapUsulan
from anjab_abk_backend.services.ai_run_sql import SqlAiRunService

URL = "/api/v1/narasi/sumber"
USULAN = "/api/v1/ai/usulan"
pytestmark = pytest.mark.usefixtures("penyedia_api")

_HIDUP = {"_env_file": None, "feature_ai_narrative_draft": True}
_TEKS = "SOP Penyusunan Perangkat Ajar. Guru wajib menyusun perangkat ajar sebelum semester."
_BADAN = {"peran_ref": "guru", "periode": "2026-27"}
KUNCI_202 = {
    "id", "fungsi", "sasaran_jenis", "sasaran_id", "job_id", "created_at", "diserap_at",
    "hasil_serap", "kode_serap", "putusan_terakhir",
}  # fmt: skip
_TABEL_NARASI = (
    NarasiKasusModel,
    NarasiVersiModel,
    NarasiVersiSumberModel,
    NarasiEventModel,
    NarasiAiPermintaanModel,
)
_DIIZINKAN_DITULIS = {"AiUsulanModel", "AiRunModel", "AsyncJobModel"}


@pytest.fixture(autouse=True)
def _klien_dilarang(monkeypatch):
    """Konstruksi klien model asli apa pun menggagalkan tes (nol panggilan jaringan)."""

    def _larang(*_a: Any, **_k: Any) -> None:
        raise AssertionError("klien model tidak boleh dibuat")

    monkeypatch.setattr(modul_klien.AnthropicKlienModel, "__init__", _larang)
    monkeypatch.setattr(modul_klien.ClaudeCliKlienModel, "__init__", _larang)


@pytest.fixture
def p01(monkeypatch):
    """Daftarkan P01 pada registri (dipulihkan otomatis)."""
    monkeypatch.setitem(FUNGSI_TERDAFTAR, "P01", FUNGSI_P01)


@pytest.fixture
def fab(db_session: Session):
    @contextmanager
    def _fab() -> Iterator[Session]:
        yield db_session

    return _fab


def _atur(app, **ubah: Any) -> None:
    cfg = Settings(**{**_HIDUP, **ubah})
    app.dependency_overrides[get_settings] = lambda: cfg


def _tim(client_as, subject: str = "tim-ekstraksi"):
    return client_as(subject, groups=["tim-kajian"])


def _sumber(
    c, teks: str = _TEKS, izin_ai: bool = True, jenis: str = "SINTETIS", menggantikan=None
) -> str:
    body: dict[str, Any] = {
        "judul": "j", "jenis": jenis, "versi": "v1", "periode": "2026-27", "teks": teks,
    }  # fmt: skip
    if izin_ai:
        body.update(izin_ai=True, izin_catatan="uji sintetis")
    if menggantikan:
        body["menggantikan_id"] = menggantikan
    r = c.post(URL, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ekstrak(c, sumber_id: str, badan: dict[str, Any] | None = None, **kw):
    return c.post(f"{URL}/{sumber_id}/ekstraksi-ai", json=_BADAN if badan is None else badan, **kw)


def _hitung(db: Session) -> tuple[int, int, int]:
    return (
        db.scalar(select(func.count()).select_from(AsyncJobModel)),
        db.scalar(select(func.count()).select_from(AiRunModel)),
        db.scalar(select(func.count()).select_from(AiUsulanModel)),
    )


def _hitung_narasi(db: Session) -> list[int]:
    db.flush()
    return [db.scalar(select(func.count()).select_from(m)) for m in _TABEL_NARASI]


def _foto_sumber(db: Session) -> list[tuple[str, str, str]]:
    db.flush()
    baris = db.scalars(select(NarasiSumberModel).order_by(NarasiSumberModel.id)).all()
    return [(b.id, b.teks, b.teks_hash) for b in baris]


def _sha(teks: str) -> str:
    return hashlib.sha256(teks.encode()).hexdigest()


def _keluaran(sumber_id: str, teks: str = _TEKS, gap: bool = False) -> dict[str, Any]:
    span = "Guru wajib menyusun perangkat ajar"
    return {
        "status": "EVIDENCE_GAP" if gap else "AI_DRAFT",
        "source_refs": [] if gap else [{"source_id": sumber_id, "source_hash": _sha(teks)}],
        "cited_spans": [] if gap else [{"source_id": sumber_id, "span": span}],
        "confidence_reason": "kutipan langsung",
        "unknowns": ["sumber tidak memuat prosedur"] if gap else [],
        "contradictions": [],
        "human_review_required": True,
        "isi": {
            "factual_extracts": []
            if gap
            else [
                {
                    "fakta": "Guru wajib menyusun perangkat ajar.",
                    "sifat": "NORMATIF",
                    "source_id": sumber_id,
                    "span": span,
                }
            ],
            "source_quality": [
                {"source_id": sumber_id, "penilaian": "CUKUP", "alasan": "teks utuh"}
            ],
            "uncertainties": [],
            "limitations": ["hanya satu dokumen"],
        },
    }


class KlienTiruan:
    """Klien model tiruan: satu jawaban tetap, mencatat panggilan."""

    def __init__(self, jawaban: dict[str, Any]) -> None:
        self.jawaban = jawaban
        self.panggilan: list[tuple[str, str, dict[str, Any]]] = []

    def panggil(self, instruksi: str, masukan_json: str, skema: dict[str, Any]) -> JawabanModel:
        self.panggilan.append((instruksi, masukan_json, skema))
        return JawabanModel(
            teks=json.dumps(self.jawaban), model_dilayani="model-tiruan",
            stop_reason="end_turn", input_tokens=5, output_tokens=5,
        )  # fmt: skip


def test_positif_202_kunci_kontrak_dan_masukan_hanya_sumber_serta_kode(
    app, client_as, db_session, p01
):
    c = _tim(client_as, "tim-positif")
    _atur(app)
    sid = _sumber(c)
    r = _ekstrak(c, sid)
    assert r.status_code == 202, r.text
    body = r.json()
    assert set(body) == KUNCI_202
    for dilarang in ("ai_run_id", "sumber_ids", "diminta_oleh", "isi", "amplop", "actor_key"):
        assert dilarang not in body
    assert "actor_key" not in r.text and body["putusan_terakhir"] is None
    assert body["fungsi"] == "P01" and body["sasaran_jenis"] == "NARASI_SUMBER"
    assert body["sasaran_id"] == sid and body["diserap_at"] is None
    rec = db_session.get(AiUsulanModel, body["id"])
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.fungsi == "P01" and run.status_qa == "MENUNGGU"
    assert run.masukan["parameter"] == _BADAN
    daftar = run.masukan["sumber"]
    assert [x["source_id"] for x in daftar] == [sid]
    assert daftar[0]["teks"] == _TEKS and daftar[0]["source_hash"] == _sha(_TEKS)
    assert rec.sumber_ids == [sid] and rec.diminta_oleh == "tim-positif"
    assert db_session.scalar(select(func.count()).select_from(NarasiAiPermintaanModel)) == 0


def test_e2e_klien_tiruan_serap_usulan_sumber_tak_berubah_dan_narasi_tak_tertulis(
    app, client_as, db_session, p01, fab
):
    c = _tim(client_as)
    _atur(app)
    sid = _sumber(c)
    sumber_lain = _sumber(c, teks="Dokumen lain yang tidak diajukan.")
    foto = _foto_sumber(db_session)
    narasi_awal = _hitung_narasi(db_session)
    ditulis: set[str] = set()

    def _catat(session: Session, _ctx: Any, _inst: Any) -> None:
        ditulis.update(type(o).__name__ for o in (*session.new, *session.dirty, *session.deleted))

    klien = KlienTiruan(_keluaran(sid))
    event.listen(db_session, "before_flush", _catat)
    try:
        r = _ekstrak(c, sid)
        assert r.status_code == 202, r.text
        uid = r.json()["id"]
        assert jalankan_satu(fab, Settings(**_HIDUP), lambda: klien, {"P01": FUNGSI_P01})
        assert serap_usulan(db_session, uid) is not None  # penyerap usulan
        penyerap.serap_tertunda(fab)  # penyerap narasi: tidak boleh menyentuh run P01
        db_session.flush()
    finally:
        event.remove(db_session, "before_flush", _catat)
    assert ditulis <= _DIIZINKAN_DITULIS, ditulis
    assert len(klien.panggilan) == 1
    instruksi, masukan_json, _skema = klien.panggilan[0]
    assert "menunjukkan yang seharusnya, bukan yang terlaksana" in instruksi
    assert json.loads(masukan_json)["parameter"] == _BADAN
    assert _hitung_narasi(db_session) == narasi_awal
    assert _foto_sumber(db_session) == foto  # teks, teks_hash, jumlah baris
    assert sumber_lain in {f[0] for f in foto}
    db_session.expire_all()
    d = c.get(f"{USULAN}/{uid}").json()
    assert d["hasil_serap"] == "USULAN_DIBUAT" and d["sasaran_jenis"] == "NARASI_SUMBER"
    assert d["isi"]["factual_extracts"][0]["sifat"] == "NORMATIF"
    assert d["isi"]["source_quality"][0]["penilaian"] == "CUKUP"
    saring = c.get(USULAN, params={"sasaran_jenis": "NARASI_SUMBER", "fungsi": "P01"}).json()
    assert [x["id"] for x in saring["items"]] == [uid]
    assert "sumber_ids" not in saring["items"][0]


def test_e2e_sumber_tak_relevan_evidence_gap_menghasilkan_usulan_gap(
    app, client_as, db_session, p01, fab
):
    c = _tim(client_as)
    _atur(app)
    sid = _sumber(c, teks="Daftar menu kantin berisi nasi dan sayur.")
    foto = _foto_sumber(db_session)
    r = _ekstrak(c, sid)
    assert r.status_code == 202, r.text
    uid = r.json()["id"]
    klien = KlienTiruan(_keluaran(sid, gap=True))
    assert jalankan_satu(fab, Settings(**_HIDUP), lambda: klien, {"P01": FUNGSI_P01})
    assert serap_usulan(db_session, uid) is not None
    db_session.flush()
    db_session.expire_all()
    assert c.get(f"{USULAN}/{uid}").json()["hasil_serap"] == "EVIDENCE_GAP"
    assert _foto_sumber(db_session) == foto


def test_keluaran_model_dengan_sifat_di_luar_enum_dikarantina_usulan_manual(
    app, client_as, db_session, p01, fab
):
    c = _tim(client_as)
    _atur(app)
    sid = _sumber(c)
    r = _ekstrak(c, sid)
    uid = r.json()["id"]
    buruk = _keluaran(sid)
    buruk["isi"]["factual_extracts"][0]["sifat"] = "TERLAKSANA"
    klien = KlienTiruan(buruk)
    assert jalankan_satu(fab, Settings(**_HIDUP), lambda: klien, {"P01": FUNGSI_P01})
    assert serap_usulan(db_session, uid) is not None
    db_session.flush()
    rec = db_session.get(AiUsulanModel, uid)
    db_session.refresh(rec)
    assert rec.hasil_serap == "MANUAL" and list(rec.kode_serap) == ["SKEMA_TIDAK_SAH"]
    assert rec.isi is None


def test_flag_mati_409_tanpa_baris_tanpa_baca_dan_tanpa_klien(app, client_as, db_session, p01):
    c = _tim(client_as)
    _atur(app, feature_ai_narrative_draft=False)
    awal = _hitung(db_session)
    # Sumber tak ada: 409 (bukan 404) membuktikan flag diperiksa sebelum membaca sumber.
    r = _ekstrak(c, str(uuid.uuid4()))
    assert r.status_code == 409 and r.json()["error"] == "feature_disabled", r.text
    assert _hitung(db_session) == awal


def test_p01_tak_terdaftar_409_fungsi_belum_aktif_tanpa_baris(app, client_as, db_session):
    c = _tim(client_as)
    _atur(app)
    sid = _sumber(c)
    awal = _hitung(db_session)
    assert "P01" not in FUNGSI_TERDAFTAR
    r = _ekstrak(c, sid)
    assert r.status_code == 409 and r.json()["error"] == "fungsi_belum_aktif", r.text
    assert _hitung(db_session) == awal


def test_sumber_tak_ada_404_tanpa_baris(app, client_as, db_session, p01):
    c = _tim(client_as)
    _atur(app)
    awal = _hitung(db_session)
    assert _ekstrak(c, str(uuid.uuid4())).status_code == 404
    assert _hitung(db_session) == awal


def test_sumber_tanpa_izin_ai_409_izin_sumber_tidak_ada_tanpa_baris(
    app, client_as, db_session, p01
):
    c = _tim(client_as)
    _atur(app)
    sid = _sumber(c, izin_ai=False)
    awal = _hitung(db_session)
    r = _ekstrak(c, sid)
    assert r.status_code == 409 and r.json()["error"] == "izin_sumber_tidak_ada", r.text
    assert _hitung(db_session) == awal


def test_sumber_sintetis_lolos_gerbang_dan_dokumen_resmi_di_luar_env_jenis_ditolak(
    app, client_as, db_session, p01
):
    c = _tim(client_as)
    _atur(app)
    ok = _ekstrak(c, _sumber(c))
    assert ok.status_code == 202, ok.text
    run_ok = db_session.get(AiRunModel, db_session.get(AiUsulanModel, ok.json()["id"]).ai_run_id)
    assert run_ok.status_qa == "MENUNGGU"
    resmi = _ekstrak(c, _sumber(c, jenis="DOKUMEN_RESMI"))
    assert resmi.status_code == 202, resmi.text  # tidak ada aturan khusus P01 yang melonggarkan
    rec = db_session.get(AiUsulanModel, resmi.json()["id"])
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.status_qa == "DIBLOKIR" and list(run.kode_qa) == ["JENIS_DITOLAK"]
    assert run.masukan is None
    assert db_session.get(AsyncJobModel, rec.job_id).status == "MANUAL_REVIEW"


def test_dokumen_resmi_lolos_bila_operator_mengizinkan_jenisnya(app, client_as, db_session, p01):
    c = _tim(client_as)
    _atur(app, ai_jenis_sumber_diizinkan=["SINTETIS", "DOKUMEN_RESMI"])
    r = _ekstrak(c, _sumber(c, jenis="DOKUMEN_RESMI"))
    assert r.status_code == 202, r.text
    run = db_session.get(AiRunModel, db_session.get(AiUsulanModel, r.json()["id"]).ai_run_id)
    assert run.status_qa == "MENUNGGU"


def test_sumber_memuat_email_sintetis_diblokir_usulan_manual_nol_klien(
    app, client_as, db_session, p01, fab
):
    c = _tim(client_as)
    _atur(app)
    email = "kontak.fiktif@contoh.example"
    sid = _sumber(c, teks=f"SOP Pengaduan: hubungi {email} untuk menyampaikan pengaduan.")
    foto = _foto_sumber(db_session)
    r = _ekstrak(c, sid)
    assert r.status_code == 202, r.text
    uid = r.json()["id"]
    rec = db_session.get(AiUsulanModel, uid)
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.status_qa == "DIBLOKIR" and list(run.kode_qa) == ["PII_DITEMUKAN"]
    assert run.masukan is None
    assert email not in json.dumps(run.kode_qa)
    assert db_session.get(AsyncJobModel, rec.job_id).status == "MANUAL_REVIEW"
    # Tidak ada job PENDING untuk worker: tidak ada klien yang dibuat (fixture melarangnya).
    klien = KlienTiruan(_keluaran(sid))
    assert jalankan_satu(fab, Settings(**_HIDUP), lambda: klien, {"P01": FUNGSI_P01}) is None
    assert klien.panggilan == []
    assert serap_usulan(db_session, uid) is not None
    db_session.flush()
    db_session.expire_all()
    rec = db_session.get(AiUsulanModel, uid)
    assert rec.hasil_serap == "MANUAL" and list(rec.kode_serap) == ["PII_DITEMUKAN"]
    assert rec.isi is None and rec.amplop is None
    assert _foto_sumber(db_session) == foto


def test_sumber_yang_digantikan_tetap_dapat_diekstraksi_tanpa_aturan_baru(
    app, client_as, db_session, p01
):
    c = _tim(client_as)
    _atur(app)
    lama = _sumber(c)
    baru = _sumber(c, teks=_TEKS + " Revisi.", menggantikan=lama)
    r_lama = _ekstrak(c, lama)
    r_baru = _ekstrak(c, baru)
    assert r_lama.status_code == 202 and r_baru.status_code == 202
    assert r_lama.json()["sasaran_id"] == lama and r_baru.json()["sasaran_id"] == baru


@pytest.mark.parametrize(
    "buruk",
    [
        "", "tahun ajaran", "a b", " a", "a ", "a\nb", "a\n", "\n", "a\r\n", "a\tb", "a\x00",
        "a;b", "a/b", "a$", "<b>", "é", "x" * 101,
    ],
)  # fmt: skip
@pytest.mark.parametrize("kolom", ["peran_ref", "periode"])
def test_parameter_teks_bebas_atau_berbahaya_422_tanpa_baris(
    app, client_as, db_session, p01, kolom, buruk
):
    c = _tim(client_as)
    _atur(app)
    sid = _sumber(c)
    awal = _hitung(db_session)
    r = _ekstrak(c, sid, {**_BADAN, kolom: buruk})
    assert r.status_code == 422, (kolom, repr(buruk), r.text)
    assert _hitung(db_session) == awal


def test_parameter_badan_kurang_atau_lebih_422_dan_nilai_sah_202(app, client_as, p01):
    c = _tim(client_as)
    _atur(app)
    sid = _sumber(c)
    assert _ekstrak(c, sid, {"peran_ref": "guru"}).status_code == 422
    assert _ekstrak(c, sid, {**_BADAN, "teks": "bebas"}).status_code == 422
    assert _ekstrak(c, sid, {}).status_code == 422
    assert _ekstrak(c, sid, {"peran_ref": "x" * 100, "periode": "GURU_1.a:b-c"}).status_code == 202


def test_kode_parameter_lolos_periksa_pii_tanpa_positif_palsu(app, client_as, db_session, p01):
    """Kode sah berbentuk tanggal/angka tidak memicu gerbang PII pada parameter."""
    c = _tim(client_as)
    _atur(app)
    for i, (peran, periode) in enumerate(
        [("guru", "2026-27"), ("wali_kelas", "2026-S1"), ("kepala_sekolah", "2026.1")]
    ):
        sid = _sumber(c, teks=f"{_TEKS} Dokumen {i}.")
        r = _ekstrak(c, sid, {"peran_ref": peran, "periode": periode})
        assert r.status_code == 202, r.text
        run = db_session.get(AiRunModel, db_session.get(AiUsulanModel, r.json()["id"]).ai_run_id)
        assert run.status_qa == "MENUNGGU", (peran, periode, run.kode_qa)


def test_idempotency_retry_setelah_sukses_membalas_tersimpan_dan_tanpa_key_409_berjalan(
    app, client_as, db_session, p01
):
    c = _tim(client_as)
    _atur(app)
    sid = _sumber(c)
    h = {"Idempotency-Key": "kunci-ekstraksi-1"}
    r1 = _ekstrak(c, sid, headers=h)
    assert r1.status_code == 202, r1.text
    awal = _hitung(db_session)
    # Tanpa key, pengajuan kedua selagi usulan berjalan: 409 usulan_berjalan.
    r_tanpa = _ekstrak(c, sid)
    assert r_tanpa.status_code == 409 and r_tanpa.json()["error"] == "usulan_berjalan"
    # Retry key sama: balasan tersimpan, tanpa baris baru.
    r2 = _ekstrak(c, sid, headers=h)
    assert r2.status_code == 200 and r2.json() == r1.json()
    assert _hitung(db_session) == awal
    # Setelah usulan diserap, tanpa key pengajuan baru sah, tetapi key lama tetap tersimpan.
    uid = r1.json()["id"]
    SqlAiRunService(db_session, Settings(**_HIDUP)).tutup(
        db_session.get(AiUsulanModel, uid).ai_run_id,
        StatusQaAi.KARANTINA, ["TANPA_SITASI"], None, None, None, None, None,
    )  # fmt: skip
    serap_usulan(db_session, uid)
    r3 = _ekstrak(c, sid, headers=h)
    assert r3.status_code == 200 and r3.json() == r1.json()
    assert _hitung(db_session) == awal


def test_penolakan_404_dan_409_dihitung_di_dalam_aksi_idempoten(app, client_as, db_session, p01):
    c = _tim(client_as)
    _atur(app)
    h = {"Idempotency-Key": "kunci-ekstraksi-izin"}
    sid = _sumber(c, izin_ai=False)
    r1 = _ekstrak(c, sid, headers=h)
    assert r1.status_code == 409 and r1.json()["error"] == "izin_sumber_tidak_ada"
    awal = _hitung(db_session)
    r2 = _ekstrak(c, sid, headers=h)
    assert r2.status_code == 409 and r2.json()["error"] == "izin_sumber_tidak_ada"
    assert _hitung(db_session) == awal


def test_otorisasi_401_403_mendahului_422_dan_404(app, anon_client, client_as, p01):
    _atur(app)
    path = f"{URL}/{uuid.uuid4()}/ekstraksi-ai"
    assert anon_client.post(path, json=_BADAN).status_code == 401
    assert anon_client.post(path, json={}).status_code == 401
    for grup in ("admin", "sekolah-pengisi"):
        c = client_as("x-" + grup, groups=[grup])
        assert c.post(path, json=_BADAN).status_code == 403, grup  # sumber tak ada: bukan 404
        assert c.post(path, json={}).status_code == 403, grup  # badan salah: bukan 422
    tim = _tim(client_as)
    assert tim.post(path, json={}).status_code == 422
    assert tim.post(path, json={"peran_ref": "a b", "periode": "2026"}).status_code == 422
    assert tim.post(path, json=_BADAN).status_code == 404


def test_openapi_memuat_rute_dan_registri_produksi_tanpa_p01(app, anon_client):
    paths = anon_client.get("/openapi.json").json()["paths"]
    rute = paths["/api/v1/narasi/sumber/{sumber_id}/ekstraksi-ai"]["post"]
    assert "202" in rute["responses"] and rute["operationId"] == "narasi_sumber_ekstraksi_ai_ajukan"
    assert "P01" not in FUNGSI_TERDAFTAR


def test_e2e_span_fakta_palsu_dengan_cited_spans_sah_usulan_manual_tanpa_isi(
    app, client_as, db_session, p01, fab
):
    c = _tim(client_as)
    _atur(app)
    sid = _sumber(c)
    r = _ekstrak(c, sid)
    assert r.status_code == 202, r.text
    uid = r.json()["id"]
    jawab = _keluaran(sid)
    jawab["isi"]["factual_extracts"][0]["span"] = "kalimat karangan model"
    assert jalankan_satu(fab, Settings(**_HIDUP), lambda: KlienTiruan(jawab), {"P01": FUNGSI_P01})
    assert serap_usulan(db_session, uid) is not None
    db_session.flush()
    db_session.expire_all()
    d = c.get(f"{USULAN}/{uid}").json()
    assert d["hasil_serap"] == "MANUAL" and d["kode_serap"] == ["SPAN_FAKTA_TIDAK_DITEMUKAN"]
    assert d["isi"] is None
    run = db_session.scalar(select(AiRunModel).where(AiRunModel.fungsi == "P01"))
    assert run.status_qa == "LOLOS"


def test_e2e_evidence_gap_tidak_diperiksa_aturan_span(app, client_as, db_session, p01, fab):
    c = _tim(client_as)
    _atur(app)
    sid = _sumber(c)
    uid = _ekstrak(c, sid).json()["id"]
    klien = KlienTiruan(_keluaran(sid, gap=True))
    assert jalankan_satu(fab, Settings(**_HIDUP), lambda: klien, {"P01": FUNGSI_P01})
    assert serap_usulan(db_session, uid) == HasilSerapUsulan.EVIDENCE_GAP
