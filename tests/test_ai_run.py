"""Test register run AI: helper hash/Protocol_ID, seam SQL, dan endpoint baca admin."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from anjab_abk_backend import __version__
from anjab_abk_backend.config import Settings
from anjab_abk_backend.errors import ConflictError, NotFoundError
from anjab_abk_backend.models import AiRunModel
from anjab_abk_backend.schemas.ai_run import AiSumber, StatusQaAi
from anjab_abk_backend.services.ai_run import bangun_protocol_id, hash_masukan
from anjab_abk_backend.services.ai_run_sql import SqlAiRunService

_BAWAAN = Settings(_env_file=None)
_SIMPAN = Settings(_env_file=None, ai_simpan_masukan=True)
_MASUKAN = {"bukti": ["a", "b"], "catatan": "rahasia-masukan"}


def _buka(db: Session, settings: Settings = _BAWAAN, fungsi: str = "draf_narasi"):
    svc = SqlAiRunService(db, settings)
    return svc, svc.buka(
        fungsi,
        "v1",
        hash_masukan("prompt"),
        "claude-x",
        [AiSumber(source_id="s1", source_hash="ab" * 32)],
        _MASUKAN,
        "tester",
    )


def _tutup(svc: SqlAiRunService, run_id: str, status: StatusQaAi = StatusQaAi.LOLOS):
    keluaran = {"teks": "rahasia-keluaran"}
    return svc.tutup(run_id, status, ["OK"], keluaran, "end_turn", "claude-y", 5, 7)


def test_hash_masukan_urutan_kunci_dan_perubahan_isi() -> None:
    assert hash_masukan({"a": 1, "b": "é"}) == hash_masukan({"b": "é", "a": 1})
    assert hash_masukan({"a": 1}) != hash_masukan({"a": 2})
    assert len(hash_masukan({})) == 64


def test_bangun_protocol_id_memuat_arm_versi_commit_fungsi_prompt() -> None:
    s = Settings(_env_file=None, ai_protocol_arm="ARM_A", app_build_commit="0123456789abcdef" * 2)
    assert bangun_protocol_id("draf_narasi", "v3", s) == (
        f"ARM_A/{__version__}+0123456789ab/draf_narasi@v3"
    )
    assert bangun_protocol_id("f", "p", _BAWAAN) == f"TANPA_ARM/{__version__}+unknown/f@p"


def test_buka_status_menunggu_dengan_jejak_terisi(db_session: Session) -> None:
    _, run = _buka(db_session)
    assert run.status_qa == StatusQaAi.MENUNGGU and run.selesai_at is None
    assert run.protocol_id and run.prompt_hash
    assert run.input_snapshot_id == hash_masukan(_MASUKAN)
    rec = db_session.get(AiRunModel, run.id)
    assert rec.masukan == _MASUKAN


def test_tutup_mengisi_hasil_dan_mengosongkan_masukan(db_session: Session) -> None:
    svc, run = _buka(db_session)
    r = _tutup(svc, run.id)
    assert r.status_qa == StatusQaAi.LOLOS and r.selesai_at is not None
    assert r.model_dilayani == "claude-y" and r.input_tokens == 5 and r.output_tokens == 7
    rec = db_session.get(AiRunModel, run.id)
    assert rec.masukan is None and rec.keluaran == {"teks": "rahasia-keluaran"}
    assert r.input_snapshot_id == run.input_snapshot_id


def test_tutup_dengan_simpan_masukan_mempertahankan_masukan(db_session: Session) -> None:
    svc, run = _buka(db_session, _SIMPAN)
    _tutup(svc, run.id)
    assert db_session.get(AiRunModel, run.id).masukan == _MASUKAN


def test_tutup_dua_kali_konflik_tanpa_mengubah_baris(db_session: Session) -> None:
    svc, run = _buka(db_session)
    _tutup(svc, run.id, StatusQaAi.LOLOS)
    with pytest.raises(ConflictError):
        _tutup(svc, run.id, StatusQaAi.GAGAL)
    rec = db_session.get(AiRunModel, run.id)
    assert rec.status_qa == "LOLOS" and rec.kode_qa == ["OK"]


def test_tutup_menunggu_dan_id_tak_dikenal(db_session: Session) -> None:
    from anjab_abk_backend.errors import ValidationAppError

    svc, run = _buka(db_session)
    with pytest.raises(ValidationAppError):
        _tutup(svc, run.id, StatusQaAi.MENUNGGU)
    with pytest.raises(NotFoundError):
        _tutup(svc, "tidak-ada")


def test_endpoint_list_dan_detail_tanpa_masukan_keluaran(
    client: TestClient, db_session: Session
) -> None:
    svc, run = _buka(db_session)
    _tutup(svc, run.id)
    _buka(db_session, fungsi="lain")
    r = client.get("/api/v1/system/ai/runs")
    assert r.status_code == 200 and r.json()["total"] == 2
    d = client.get(f"/api/v1/system/ai/runs/{run.id}")
    assert d.status_code == 200
    for body in (d.json(), *r.json()["items"]):
        assert "masukan" not in body and "keluaran" not in body
        assert body["protocol_id"] and body["input_snapshot_id"]
    assert "rahasia" not in r.text and "rahasia" not in d.text


def test_endpoint_filter_fungsi_dan_status(client: TestClient, db_session: Session) -> None:
    svc, run = _buka(db_session)
    _tutup(svc, run.id, StatusQaAi.KARANTINA)
    _buka(db_session, fungsi="lain")
    j = client.get("/api/v1/system/ai/runs", params={"fungsi": "lain"}).json()
    assert j["total"] == 1 and j["items"][0]["fungsi"] == "lain"
    j = client.get("/api/v1/system/ai/runs", params={"status_qa": "KARANTINA"}).json()
    assert j["total"] == 1 and j["items"][0]["id"] == run.id
    j = client.get("/api/v1/system/ai/runs", params={"status_qa": "MENUNGGU"}).json()
    assert j["total"] == 1 and j["items"][0]["fungsi"] == "lain"
    assert client.get("/api/v1/system/ai/runs", params={"status_qa": "ngawur"}).status_code == 422


def test_endpoint_otorisasi_dan_404(anon_client: TestClient, client_as) -> None:
    assert anon_client.get("/api/v1/system/ai/runs").status_code == 401
    assert anon_client.get("/api/v1/system/ai/runs/x").status_code == 401
    biasa = client_as("biasa", groups=["partisipan"])
    assert biasa.get("/api/v1/system/ai/runs").status_code == 403
    assert biasa.get("/api/v1/system/ai/runs/x").status_code == 403
    admin = client_as("admin-x", groups=["admin"])
    assert admin.get("/api/v1/system/ai/runs/tidak-ada").status_code == 404
