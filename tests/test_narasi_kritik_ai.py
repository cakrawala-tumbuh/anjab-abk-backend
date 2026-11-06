"""Tes rute `POST /api/v1/narasi/kasus/{id}/kritik-ai` (P09): hanya usulan, bukan bukti.

Klien model tidak pernah dibuat; data sintetis; tanpa jaringan. Hasil kritik hanya boleh
mendarat di `ai_usulan` (plus `ai_run` dan `async_job`), tidak di tabel `narasi_*`.
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
from anjab_abk_backend.ai.fungsi_p09 import FUNGSI_P09, id_sumber_versi
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.penyerap_usulan import serap_usulan
from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.models import (
    AiRunModel,
    AiUsulanModel,
    AsyncJobModel,
    NarasiAiPermintaanModel,
    NarasiEventModel,
    NarasiKasusModel,
    NarasiVersiModel,
    NarasiVersiSumberModel,
)
from anjab_abk_backend.narasi import penyerap
from anjab_abk_backend.narasi.schemas.kasus import RevisionOrigin, StatusNarasi
from anjab_abk_backend.narasi.schemas.mesin import AKTOR_AI_WORKER, AktorNarasi
from anjab_abk_backend.narasi.services.narasi_sql import SqlNarasiService
from anjab_abk_backend.schemas.ai_run import StatusQaAi
from anjab_abk_backend.services.ai_run_sql import SqlAiRunService

URL = "/api/v1/narasi/kasus"
SUMBER = "/api/v1/narasi/sumber"
ANTREAN = "/api/v1/narasi/antrean"
USULAN = "/api/v1/ai/usulan"
pytestmark = pytest.mark.usefixtures("penyedia_api")

_HIDUP = {"_env_file": None, "feature_ai_narrative_draft": True}
_TEKS_SUMBER = "Guru menyusun perangkat ajar pada awal semester."
_DRAF = "Guru menyusun perangkat ajar pada awal semester dan seluruh siswa tuntas."
# Sepuluh kunci kontrak respons 202 (sembilan field #102 + putusan_terakhir #103).
KUNCI_202 = {
    "id", "fungsi", "sasaran_jenis", "sasaran_id", "job_id", "created_at", "diserap_at",
    "hasil_serap", "kode_serap", "putusan_terakhir",
}  # fmt: skip
_TABEL_NARASI = (
    NarasiEventModel,
    NarasiVersiModel,
    NarasiVersiSumberModel,
    NarasiAiPermintaanModel,
)


@pytest.fixture(autouse=True)
def _klien_dilarang(monkeypatch):
    """Konstruksi klien model apa pun menggagalkan tes (nol panggilan jaringan)."""

    def _larang(*_a: Any, **_k: Any) -> None:
        raise AssertionError("klien model tidak boleh dibuat")

    monkeypatch.setattr(modul_klien.AnthropicKlienModel, "__init__", _larang)
    monkeypatch.setattr(modul_klien.ClaudeCliKlienModel, "__init__", _larang)


@pytest.fixture
def p09(monkeypatch):
    """Daftarkan P09 pada registri (dipulihkan otomatis)."""
    monkeypatch.setitem(FUNGSI_TERDAFTAR, "P09", FUNGSI_P09)


@pytest.fixture
def fab(db_session: Session):
    @contextmanager
    def _fab() -> Iterator[Session]:
        yield db_session

    return _fab


def _atur(app, **ubah: Any) -> None:
    cfg = Settings(**{**_HIDUP, **ubah})
    app.dependency_overrides[get_settings] = lambda: cfg


def _tim(client_as, subject: str = "tim-kritik"):
    return client_as(subject, groups=["tim-kajian"])


def _kasus(c, **ubah) -> dict:
    body = {
        "instrument_id": "wcp",
        "field_key": f"f-{uuid.uuid4().hex[:8]}",
        "peran_ref": "guru",
        "periode": "2026-27",
        "narrative_kind": "F1_FORMAL",
        "intended_use": "uji",
        "permission_scope": "internal",
        "sensitivity_class": "NONPRIBADI",
    }
    body.update(ubah)
    r = c.post(URL, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _sumber(c, teks: str = _TEKS_SUMBER, izin_ai: bool = True, jenis: str = "SINTETIS") -> str:
    body = {"judul": "j", "jenis": jenis, "versi": "v1", "periode": "2026-27", "teks": teks}
    if izin_ai:
        body.update(izin_ai=True, izin_catatan="uji sintetis")
    r = c.post(SUMBER, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _revisi(c, narasi_id: str, sumber_ids: list[str], teks: str = _DRAF, supersedes=None) -> dict:
    r = c.post(
        f"{URL}/{narasi_id}/revisi",
        json={
            "teks": teks,
            "sumber": [
                {"sumber_id": s, "basis_relation": "DIRECT", "source_span": "1-5"}
                for s in sumber_ids
            ],
            "supersedes_id": supersedes,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _siap(c, **kw) -> tuple[dict, str, dict]:
    """Kasus + satu sumber berizin + satu versi bertulis teks."""
    k = _kasus(c)
    sid = _sumber(c, **kw)
    return k, sid, _revisi(c, k["id"], [sid])


def _kritik(c, narasi_id: str, versi_id: str, **kw):
    return c.post(f"{URL}/{narasi_id}/kritik-ai", json={"narasi_versi_id": versi_id}, **kw)


def _hitung(db: Session) -> tuple[int, int, int]:
    return (
        db.scalar(select(func.count()).select_from(AsyncJobModel)),
        db.scalar(select(func.count()).select_from(AiRunModel)),
        db.scalar(select(func.count()).select_from(AiUsulanModel)),
    )


def _hitung_narasi(db: Session) -> list[int]:
    db.flush()
    return [db.scalar(select(func.count()).select_from(m)) for m in _TABEL_NARASI]


def _keluaran(versi_id: str) -> dict[str, Any]:
    sid = id_sumber_versi(versi_id)
    return {
        "status": "AI_DRAFT",
        "source_refs": [{"source_id": sid, "source_hash": "h"}],
        "cited_spans": [{"source_id": sid, "span": "seluruh siswa tuntas"}],
        "confidence_reason": "kutipan langsung",
        "unknowns": [],
        "contradictions": [],
        "human_review_required": True,
        "isi": {
            "peran": "REVIEWER_OTOMATIS_PEMBANTU",
            "blocking_findings": [
                {
                    "temuan": "klaim tanpa dasar",
                    "kategori": "KLAIM_TANPA_DASAR",
                    "source_id": sid,
                    "span": "seluruh siswa tuntas",
                }
            ],
            "major_findings": [],
            "correction_proposals": [],
            "limitations": ["tidak memeriksa makna"],
        },
    }


def _tutup(db: Session, run_id: str, status: StatusQaAi, kode, keluaran) -> None:
    SqlAiRunService(db, Settings(**_HIDUP)).tutup(
        run_id, status, kode, keluaran, None, None, None, None
    )


def test_positif_202_kunci_kontrak_dan_masukan_memuat_draf_sebagai_sumber(
    app, client_as, db_session, p09
):
    c = _tim(client_as, "tim-positif")
    _atur(app)
    k, sid, v = _siap(c)
    r = _kritik(c, k["id"], v["id"])
    assert r.status_code == 202, r.text
    body = r.json()
    assert set(body) == KUNCI_202
    for dilarang in ("ai_run_id", "sumber_ids", "diminta_oleh", "isi", "amplop"):
        assert dilarang not in body
    assert body["fungsi"] == "P09" and body["sasaran_jenis"] == "NARASI_KASUS"
    assert body["sasaran_id"] == k["id"] and body["diserap_at"] is None
    rec = db_session.get(AiUsulanModel, body["id"])
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.fungsi == "P09" and run.status_qa == "MENUNGGU"
    assert run.masukan["parameter"] == {"narasi_versi_id": v["id"]}
    daftar = run.masukan["sumber"]
    assert [x["source_id"] for x in daftar] == [sid, id_sumber_versi(v["id"])]
    draf = daftar[1]
    assert draf["teks"] == _DRAF and draf["jenis"] == "SINTETIS"
    assert draf["source_hash"] == hashlib.sha256(_DRAF.encode()).hexdigest()
    assert rec.sumber_ids == [sid, id_sumber_versi(v["id"])] and rec.diminta_oleh == "tim-positif"
    # Pasangan rute #98 tidak dipakai: tidak ada baris permintaan narasi.
    assert db_session.scalar(select(func.count()).select_from(NarasiAiPermintaanModel)) == 0


def test_bukan_bukti_tidak_menulis_narasi_dan_antrean_tetap(app, client_as, db_session, p09, fab):
    c = _tim(client_as)
    _atur(app)
    k, _sid, v = _siap(c)
    status_awal = db_session.get(NarasiKasusModel, k["id"]).status
    antrean_awal = c.get(ANTREAN).json()
    narasi_awal = _hitung_narasi(db_session)
    ditulis: set[str] = set()

    def _catat(session: Session, _ctx: Any, _inst: Any) -> None:
        ditulis.update(type(o).__name__ for o in (*session.new, *session.dirty, *session.deleted))

    event.listen(db_session, "before_flush", _catat)
    try:
        r = _kritik(c, k["id"], v["id"])
        assert r.status_code == 202, r.text
        uid = r.json()["id"]
        run_id = db_session.get(AiUsulanModel, uid).ai_run_id
        _tutup(db_session, run_id, StatusQaAi.LOLOS, [], _keluaran(v["id"]))
        assert serap_usulan(db_session, uid) is not None  # jalur penyerap usulan
        penyerap.serap_tertunda(fab)  # penyerap narasi: tidak boleh menyentuh run P09
        db_session.flush()
    finally:
        event.remove(db_session, "before_flush", _catat)
    assert ditulis <= {"AiUsulanModel", "AiRunModel", "AsyncJobModel"}, ditulis
    assert _hitung_narasi(db_session) == narasi_awal
    db_session.expire_all()
    assert db_session.get(NarasiKasusModel, k["id"]).status == status_awal
    assert c.get(ANTREAN).json() == antrean_awal
    d = c.get(f"{USULAN}/{uid}").json()
    assert d["hasil_serap"] == "USULAN_DIBUAT" and d["isi"]["peran"] == "REVIEWER_OTOMATIS_PEMBANTU"
    # Keputusan: `versi:<id>` ikut sumber_ids (rekaman jujur masukan) dan hanya terbaca di detail.
    assert d["sumber_ids"][-1] == id_sumber_versi(v["id"])
    daftar = c.get(USULAN, params={"fungsi": "P09"}).json()["items"][0]
    assert "sumber_ids" not in daftar


def test_flag_mati_409_tanpa_baris_tanpa_baca_dan_tanpa_klien(app, client_as, db_session, p09):
    c = _tim(client_as)
    _atur(app, feature_ai_narrative_draft=False)
    awal = _hitung(db_session)
    # Kasus dan versi tak ada: 409 (bukan 404) membuktikan flag diperiksa sebelum membaca.
    r = _kritik(c, str(uuid.uuid4()), str(uuid.uuid4()))
    assert r.status_code == 409 and r.json()["error"] == "feature_disabled", r.text
    assert _hitung(db_session) == awal


def test_p09_tak_terdaftar_409_fungsi_belum_aktif_tanpa_baris(app, client_as, db_session):
    c = _tim(client_as)
    _atur(app)
    k, _sid, v = _siap(c)
    awal = _hitung(db_session)
    assert "P09" not in FUNGSI_TERDAFTAR
    r = _kritik(c, k["id"], v["id"])
    assert r.status_code == 409 and r.json()["error"] == "fungsi_belum_aktif", r.text
    assert _hitung(db_session) == awal


def test_kasus_tak_ada_404(app, client_as, p09):
    c = _tim(client_as)
    _atur(app)
    assert _kritik(c, str(uuid.uuid4()), str(uuid.uuid4())).status_code == 404


def test_versi_basi_dan_versi_asing_409_versi_basi(app, client_as, db_session, p09):
    c = _tim(client_as)
    _atur(app)
    k, sid, v1 = _siap(c)
    _revisi(c, k["id"], [sid], teks="revisi dua", supersedes=v1["id"])
    awal = _hitung(db_session)
    for versi_id in (v1["id"], str(uuid.uuid4())):
        r = _kritik(c, k["id"], versi_id)
        assert r.status_code == 409 and r.json()["error"] == "versi_basi", r.text
    assert _hitung(db_session) == awal


def test_kasus_tanpa_versi_409_versi_basi(app, client_as, p09):
    c = _tim(client_as)
    _atur(app)
    k = _kasus(c)
    r = _kritik(c, k["id"], str(uuid.uuid4()))
    assert r.status_code == 409 and r.json()["error"] == "versi_basi"


def test_versi_tanpa_teks_409_narasi_tanpa_teks(app, client_as, db_session, p09):
    c = _tim(client_as)
    _atur(app)
    k = _kasus(c)
    v = SqlNarasiService(db_session).tambah_versi(
        k["id"],
        revision_origin=RevisionOrigin.AI_DRAFT,
        status_hasil=StatusNarasi.NEED_FACT,
        teks=None,
        sumber=[],
        supersedes_id=None,
        aktor=AktorNarasi(key=AKTOR_AI_WORKER, role="SYSTEM"),
    )
    awal = _hitung(db_session)
    r = _kritik(c, k["id"], v.id)
    assert r.status_code == 409 and r.json()["error"] == "narasi_tanpa_teks", r.text
    assert _hitung(db_session) == awal


def test_versi_tanpa_sumber_409_kritik_tanpa_sumber(app, client_as, db_session, p09, monkeypatch):
    """`tambah_versi` menolak versi berteks tanpa sumber (`NO_SOURCE_NO_FACT`), jadi kasus ini
    hanya terjangkau bila tautan sumber hilang; pemeriksaan pembela diuji dengan tautan kosong."""
    c = _tim(client_as)
    _atur(app)
    k, _sid, v = _siap(c)
    monkeypatch.setattr(SqlNarasiService, "sumber_versi", lambda _self, _vid: [])
    awal = _hitung(db_session)
    r = _kritik(c, k["id"], v["id"])
    assert r.status_code == 409 and r.json()["error"] == "kritik_tanpa_sumber", r.text
    assert _hitung(db_session) == awal


def test_sumber_tanpa_izin_ai_409_izin_sumber_tidak_ada(app, client_as, db_session, p09):
    c = _tim(client_as)
    _atur(app)
    k, _sid, v = _siap(c, izin_ai=False)
    awal = _hitung(db_session)
    r = _kritik(c, k["id"], v["id"])
    assert r.status_code == 409 and r.json()["error"] == "izin_sumber_tidak_ada", r.text
    assert _hitung(db_session) == awal


def test_draf_memuat_email_sintetis_diblokir_usulan_manual_nol_klien(
    app, client_as, db_session, p09
):
    c = _tim(client_as)
    _atur(app)
    k = _kasus(c)
    sid = _sumber(c)
    email = "kontak.fiktif@contoh.example"
    v = _revisi(c, k["id"], [sid], teks=f"Guru menyusun perangkat ajar; hubungi {email}.")
    r = _kritik(c, k["id"], v["id"])
    assert r.status_code == 202, r.text
    uid = r.json()["id"]
    rec = db_session.get(AiUsulanModel, uid)
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.status_qa == "DIBLOKIR" and list(run.kode_qa) == ["PII_DITEMUKAN"]
    assert run.masukan is None  # run ditutup: masukan (tersamarkan atau kosong) tidak disimpan
    assert email not in json.dumps(run.kode_qa)
    job = db_session.get(AsyncJobModel, rec.job_id)
    assert job.status == "MANUAL_REVIEW"
    assert serap_usulan(db_session, uid) is not None
    db_session.flush()
    db_session.expire_all()
    rec = db_session.get(AiUsulanModel, uid)
    assert rec.hasil_serap == "MANUAL" and list(rec.kode_serap) == ["PII_DITEMUKAN"]
    assert rec.isi is None and rec.amplop is None


def test_sumber_jenis_campuran_ditolak_walau_draf_memakai_jenis_sumber_pertama(
    app, client_as, db_session, p09
):
    c = _tim(client_as)
    _atur(app)
    k = _kasus(c)
    ok = _sumber(c)
    ditolak = _sumber(c, jenis="DOKUMEN_RESMI")
    v = _revisi(c, k["id"], [ok, ditolak])
    r = _kritik(c, k["id"], v["id"])
    assert r.status_code == 202, r.text
    run = db_session.get(AiRunModel, db_session.get(AiUsulanModel, r.json()["id"]).ai_run_id)
    assert run.status_qa == "DIBLOKIR" and list(run.kode_qa) == ["JENIS_DITOLAK"]
    assert run.masukan is None


def test_idempotency_retry_setelah_sukses_dan_setelah_versi_baru_membalas_tersimpan(
    app, client_as, db_session, p09
):
    c = _tim(client_as)
    _atur(app)
    k, sid, v1 = _siap(c)
    h = {"Idempotency-Key": "kunci-kritik-1"}
    r1 = _kritik(c, k["id"], v1["id"], headers=h)
    assert r1.status_code == 202, r1.text
    awal = _hitung(db_session)
    # Tanpa key, permintaan sama kini 409 `usulan_berjalan` (usulan belum diserap).
    r_tanpa = _kritik(c, k["id"], v1["id"])
    assert r_tanpa.status_code == 409 and r_tanpa.json()["error"] == "usulan_berjalan"
    # Retry key sama: balasan tersimpan, tanpa baris baru.
    r2 = _kritik(c, k["id"], v1["id"], headers=h)
    assert r2.status_code == 200 and r2.json() == r1.json()
    assert _hitung(db_session) == awal
    # Versi baru muncul (+ usulan diserap): retry key sama tetap membalas tersimpan,
    # bukan `versi_basi`; key baru untuk versi lama memang `versi_basi`.
    v2 = _revisi(c, k["id"], [sid], teks="revisi dua", supersedes=v1["id"])
    uid = r1.json()["id"]
    _tutup(
        db_session,
        db_session.get(AiUsulanModel, uid).ai_run_id,
        StatusQaAi.KARANTINA,
        ["TANPA_SITASI"],
        None,
    )
    serap_usulan(db_session, uid)
    r3 = _kritik(c, k["id"], v1["id"], headers=h)
    assert r3.status_code == 200 and r3.json() == r1.json()
    r4 = _kritik(c, k["id"], v1["id"], headers={"Idempotency-Key": "kunci-kritik-2"})
    assert r4.status_code == 409 and r4.json()["error"] == "versi_basi"
    assert _hitung(db_session) == awal
    assert v2["revision_no"] == 2


def test_otorisasi_401_403_mendahului_422_dan_404(app, anon_client, client_as, p09):
    _atur(app)
    kid = str(uuid.uuid4())
    path = f"{URL}/{kid}/kritik-ai"
    valid = {"narasi_versi_id": str(uuid.uuid4())}
    assert anon_client.post(path, json=valid).status_code == 401
    assert anon_client.post(path, json={}).status_code == 401
    for grup in ("admin", "sekolah-pengisi"):
        c = client_as("x-" + grup, groups=[grup])
        assert c.post(path, json=valid).status_code == 403, grup  # kasus tak ada: bukan 404
        assert c.post(path, json={}).status_code == 403, grup  # badan salah: bukan 422
    tim = _tim(client_as)
    assert tim.post(path, json={}).status_code == 422
    assert tim.post(path, json={"narasi_versi_id": "teks bebas"}).status_code == 422
    assert tim.post(path, json={**valid, "teks": "x"}).status_code == 422
    assert tim.post(path, json=valid).status_code == 404


def test_openapi_memuat_rute_dan_registri_produksi_tanpa_p09(app, anon_client):
    paths = anon_client.get("/openapi.json").json()["paths"]
    rute = paths["/api/v1/narasi/kasus/{narasi_id}/kritik-ai"]["post"]
    assert "202" in rute["responses"] and rute["operationId"] == "narasi_kasus_kritik_ai_ajukan"
    assert "P09" not in FUNGSI_TERDAFTAR


def test_riwayat_kasus_tak_berubah_setelah_kritik(app, client_as, p09):
    """Kritik tidak menambah versi maupun event: riwayat kasus identik sebelum dan sesudah."""
    c = _tim(client_as)
    _atur(app)
    k, _sid, v = _siap(c)
    sebelum = c.get(f"{URL}/{k['id']}/riwayat").json()
    assert _kritik(c, k["id"], v["id"]).status_code == 202
    assert c.get(f"{URL}/{k['id']}/riwayat").json() == sebelum
