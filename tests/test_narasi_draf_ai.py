"""Tes rute pengaju draf AI `/api/v1/narasi/kasus/{id}/draf-ai` dan `/permintaan-ai`.

Klien model tidak pernah dibuat; data sumber sintetis; tanpa jaringan.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session

from anjab_abk_backend.ai import klien as modul_klien
from anjab_abk_backend.ai.fungsi_p10 import FUNGSI_P10
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.models import (
    AiRunModel,
    AsyncJobModel,
    NarasiAiPermintaanModel,
)
from anjab_abk_backend.schemas.common import FiturKode
from anjab_abk_backend.services.ai_saklar_sql import SqlSaklarAiService

URL = "/api/v1/narasi/kasus"
SUMBER = "/api/v1/narasi/sumber"
_HIDUP = {"_env_file": None, "feature_ai_narrative_draft": True}
_TEKS = "Guru mengajar kelas lima setiap hari."


@pytest.fixture(autouse=True)
def _klien_dilarang(monkeypatch):
    """Konstruksi klien model apa pun menggagalkan tes."""

    def _larang(*_a: Any, **_k: Any) -> None:
        raise AssertionError("klien model tidak boleh dibuat")

    monkeypatch.setattr(modul_klien.AnthropicKlienModel, "__init__", _larang)


@pytest.fixture
def p10(monkeypatch):
    """Daftarkan P10 pada registri (dipulihkan otomatis)."""
    monkeypatch.setitem(FUNGSI_TERDAFTAR, "P10", FUNGSI_P10)


def _atur(app, **ubah: Any) -> None:
    cfg = Settings(**{**_HIDUP, **ubah})
    app.dependency_overrides[get_settings] = lambda: cfg


def _tim(client_as, subject: str = "tim-ai"):
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


def _sumber(c, teks: str = _TEKS, izin_ai: bool = True) -> str:
    body = {"judul": "j", "jenis": "SINTETIS", "versi": "v1", "periode": "2026-27", "teks": teks}
    if izin_ai:
        body.update(izin_ai=True, izin_catatan="uji sintetis")
    r = c.post(SUMBER, json=body)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _hitung(db: Session) -> tuple[int, int, int]:
    return (
        db.query(AsyncJobModel).count(),
        db.query(AiRunModel).count(),
        db.query(NarasiAiPermintaanModel).count(),
    )


def test_flag_mati_409_tanpa_tulisan_tanpa_baca_dan_tanpa_klien(app, client_as, db_session):
    c = _tim(client_as)
    _atur(app, feature_ai_narrative_draft=False)
    awal = _hitung(db_session)
    ditulis: list[str] = []

    def _catat(session: Session, _ctx: Any, _inst: Any) -> None:
        ditulis.extend(type(o).__name__ for o in (*session.new, *session.dirty, *session.deleted))

    event.listen(db_session, "before_flush", _catat)
    try:
        # id kasus tidak ada: 409 (bukan 404) membuktikan flag diperiksa sebelum membaca.
        r = c.post(f"{URL}/{uuid.uuid4()}/draf-ai", json={"sumber_ids": []})
    finally:
        event.remove(db_session, "before_flush", _catat)
    assert r.status_code == 409 and r.json()["error"] == "feature_disabled", r.text
    assert ditulis == [] and _hitung(db_session) == awal


def test_saklar_dimatikan_409_manual_tetap_200(app, client_as, db_session, p10):
    c = _tim(client_as)
    _atur(app)
    k = _kasus(c)
    cfg = Settings(**_HIDUP)
    SqlSaklarAiService(db_session, cfg).matikan(FiturKode.AI_NARRATIVE_DRAFT, "uji", "tester")
    awal = _hitung(db_session)
    r = c.post(f"{URL}/{k['id']}/draf-ai", json={"sumber_ids": []})
    assert r.status_code == 409 and r.json()["error"] == "feature_disabled"
    assert _hitung(db_session) == awal
    assert c.get(f"{URL}/{k['id']}").status_code == 200


def test_positif_202_dan_tautan_benar(app, client_as, db_session, p10):
    c = _tim(client_as, "tim-positif")
    _atur(app)
    k = _kasus(c)
    sid = _sumber(c)
    r = c.post(f"{URL}/{k['id']}/draf-ai", json={"sumber_ids": [sid]})
    assert r.status_code == 202, r.text
    p = r.json()
    assert p["job_status"] == "PENDING" and p["sumber_ids"] == [sid]
    assert "keluaran" not in p and "masukan" not in p
    rec = db_session.get(NarasiAiPermintaanModel, p["id"])
    job = db_session.get(AsyncJobModel, rec.job_id)
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert rec.narasi_id == k["id"] and rec.diminta_oleh == "tim-positif"
    assert job.ref_id == run.id == rec.ai_run_id and run.fungsi == "P10"
    assert run.status_qa == "MENUNGGU" and run.masukan["ref_id"] is None
    assert run.masukan["parameter"]["field_key"] == k["field_key"]
    assert run.masukan["sumber"][0]["source_id"] == sid


def test_sumber_kosong_berakhir_evidence_gap_tanpa_model(app, client_as, db_session, p10):
    c = _tim(client_as)
    _atur(app)
    k = _kasus(c)
    r = c.post(f"{URL}/{k['id']}/draf-ai", json={"sumber_ids": []})
    assert r.status_code == 202, r.text
    assert r.json()["job_status"] == "MANUAL_REVIEW"
    rec = db_session.get(NarasiAiPermintaanModel, r.json()["id"])
    assert db_session.get(AiRunModel, rec.ai_run_id).status_qa == "EVIDENCE_GAP"


def test_sumber_memuat_pii_run_diblokir(app, client_as, db_session, p10):
    c = _tim(client_as)
    _atur(app)
    k = _kasus(c)
    sid = _sumber(c, teks="Hubungi tester@example.com untuk jadwal.")
    r = c.post(f"{URL}/{k['id']}/draf-ai", json={"sumber_ids": [sid]})
    assert r.status_code == 202, r.text
    rec = db_session.get(NarasiAiPermintaanModel, r.json()["id"])
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.status_qa == "DIBLOKIR" and run.kode_qa == ["PII_DITEMUKAN"]


def test_izin_ai_false_409_tanpa_baris(app, client_as, db_session, p10):
    c = _tim(client_as)
    _atur(app)
    k = _kasus(c)
    sid = _sumber(c, izin_ai=False)
    awal = _hitung(db_session)
    r = c.post(f"{URL}/{k['id']}/draf-ai", json={"sumber_ids": [sid]})
    assert r.status_code == 409 and r.json()["error"] == "izin_sumber_tidak_ada"
    assert _hitung(db_session) == awal


def test_samarkan_409(app, client_as, db_session, p10):
    c = _tim(client_as)
    _atur(app, ai_pii_mode="SAMARKAN")
    k = _kasus(c)
    awal = _hitung(db_session)
    r = c.post(f"{URL}/{k['id']}/draf-ai", json={"sumber_ids": []})
    assert r.status_code == 409 and r.json()["error"] == "pii_mode_belum_didukung"
    assert _hitung(db_session) == awal


def test_status_salah_409(app, client_as, db_session, p10):
    c = _tim(client_as)
    _atur(app)
    k = _kasus(c)
    sid = _sumber(c)
    rv = c.post(
        f"{URL}/{k['id']}/revisi",
        json={"teks": "manual", "sumber": [{"sumber_id": sid, "basis_relation": "DIRECT"}]},
    )
    assert rv.status_code == 201
    r = c.post(f"{URL}/{k['id']}/draf-ai", json={"sumber_ids": []})
    assert r.status_code == 409 and r.json()["error"] == "narasi_status_tidak_sah"


def test_permintaan_berjalan_409(app, client_as, db_session, p10):
    c = _tim(client_as)
    _atur(app)
    k = _kasus(c)
    assert c.post(f"{URL}/{k['id']}/draf-ai", json={"sumber_ids": []}).status_code == 202
    awal = _hitung(db_session)
    r = c.post(f"{URL}/{k['id']}/draf-ai", json={"sumber_ids": []})
    assert r.status_code == 409 and r.json()["error"] == "permintaan_berjalan"
    assert _hitung(db_session) == awal


def test_sumber_tak_dikenal_422_dan_kasus_tak_ada_404(app, client_as, db_session, p10):
    c = _tim(client_as)
    _atur(app)
    k = _kasus(c)
    r = c.post(f"{URL}/{k['id']}/draf-ai", json={"sumber_ids": [str(uuid.uuid4())]})
    assert r.status_code == 422
    assert c.post(f"{URL}/{uuid.uuid4()}/draf-ai", json={"sumber_ids": []}).status_code == 404


def test_p10_tak_terdaftar_409_fungsi_belum_aktif(app, client_as, db_session):
    c = _tim(client_as)
    _atur(app)
    assert "P10" not in FUNGSI_TERDAFTAR
    k = _kasus(c)
    awal = _hitung(db_session)
    r = c.post(f"{URL}/{k['id']}/draf-ai", json={"sumber_ids": []})
    assert r.status_code == 409 and r.json()["error"] == "fungsi_belum_aktif"
    assert _hitung(db_session) == awal


def test_get_permintaan_ai_tanpa_masukan_keluaran(app, client_as, db_session, p10):
    c = _tim(client_as)
    _atur(app)
    k = _kasus(c)
    sid = _sumber(c)
    assert c.get(f"{URL}/{k['id']}/permintaan-ai").json()["total"] == 0
    post = c.post(f"{URL}/{k['id']}/draf-ai", json={"sumber_ids": [sid]}).json()
    r = c.get(f"{URL}/{k['id']}/permintaan-ai")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert set(item) == {
        "id",
        "job_id",
        "job_status",
        "job_error_code",
        "ai_run_id",
        "sumber_ids",
        "created_at",
        "diserap_at",
        "hasil_serap",
        "kode_serap",
    }
    assert item["id"] == post["id"] and item["diserap_at"] is None
    assert c.get(f"{URL}/{uuid.uuid4()}/permintaan-ai").status_code == 404


def test_otorisasi_dua_rute(app, anon_client, client_as):
    _atur(app)
    kid = str(uuid.uuid4())
    for metode, path, kw in (
        ("post", f"{URL}/{kid}/draf-ai", {"json": {"sumber_ids": []}}),
        ("get", f"{URL}/{kid}/permintaan-ai", {}),
    ):
        assert getattr(anon_client, metode)(path, **kw).status_code == 401
        for grup in ("admin", "sekolah-pengisi"):
            r = getattr(client_as("x-" + grup, groups=[grup]), metode)(path, **kw)
            assert r.status_code == 403, (path, grup)


def test_openapi_memuat_rute_pengaju_dan_registri_produksi_kosong(app, anon_client):
    paths = anon_client.get("/openapi.json").json()["paths"]
    draf = paths["/api/v1/narasi/kasus/{narasi_id}/draf-ai"]["post"]
    assert "202" in draf["responses"]
    assert "/api/v1/narasi/kasus/{narasi_id}/permintaan-ai" in paths
    assert "P10" not in FUNGSI_TERDAFTAR
