"""Tes rute `POST /api/v1/task-inventory/jabatan/{id}/normalisasi-ai` (P02) dan helper rangkaian.

Klien model sungguhan tidak pernah dibuat; data sintetis; tanpa jaringan. Hasil hanya boleh
mendarat di `ai_usulan` (plus `ai_run` dan `async_job`); katalog TI tidak ditulis.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from anjab_abk_backend.ai import klien as modul_klien
from anjab_abk_backend.ai.fungsi_p02 import FIELD_SUMBER_KATALOG_TI, FUNGSI_P02
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.errors import NotFoundError
from anjab_abk_backend.models import (
    AiRunModel,
    AiUsulanModel,
    AiUsulanPutusanModel,
    JabatanModel,
    TiTugasPokokModel,
    TiUraianTugasJabatanModel,
    TiUraianTugasModel,
)
from anjab_abk_backend.services.ai_usulan import UsulanBelumDiterimaError
from anjab_abk_backend.services.ai_usulan_sql import SqlAiUsulanService

URL = "/api/v1/task-inventory/jabatan"
SUMBER = "/api/v1/narasi/sumber"
pytestmark = pytest.mark.usefixtures("penyedia_api")

_HIDUP = {
    "_env_file": None,
    "feature_ai_narrative_draft": True,
    "ai_jenis_sumber_diizinkan": ["SINTETIS", "KATALOG_TI"],
}
_BADAN = {"periode": "2026/27"}
_DASAR = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _klien_dilarang(monkeypatch):
    """Konstruksi klien model asli apa pun menggagalkan tes (nol panggilan jaringan)."""

    def _larang(*_a: Any, **_k: Any) -> None:
        raise AssertionError("klien model tidak boleh dibuat")

    monkeypatch.setattr(modul_klien.AnthropicKlienModel, "__init__", _larang)
    monkeypatch.setattr(modul_klien.ClaudeCliKlienModel, "__init__", _larang)


@pytest.fixture
def p02(monkeypatch):
    """Daftarkan P02 pada registri (dipulihkan otomatis)."""
    monkeypatch.setitem(FUNGSI_TERDAFTAR, "P02", FUNGSI_P02)


def _atur(app, **ubah: Any) -> Settings:
    cfg = Settings(**{**_HIDUP, **ubah})
    app.dependency_overrides[get_settings] = lambda: cfg
    return cfg


def _tim(client_as, subject: str = "tim-p02"):
    return client_as(subject, groups=["tim-kajian"])


def _jabatan(db: Session, panjang: int = 40, kode: str | None = None) -> str:
    jid = ("jbt_" + uuid.uuid4().hex * 2)[:panjang]
    db.add(
        JabatanModel(
            id=jid, kode=kode or f"P2-{uuid.uuid4().hex[:8]}", nama="Jabatan Uji P02",
            jenis="struktural",
        )
    )  # fmt: skip
    db.flush()
    return jid


def _uraian(db: Session, jabatan_id: str, n: int, unit: str = "SD") -> list[str]:
    tp = TiTugasPokokModel(id=f"tp_{uuid.uuid4().hex[:12]}", nama=f"Pokok {uuid.uuid4().hex}")
    db.add(tp)
    db.flush()
    ids = []
    for i in range(n):
        ut = TiUraianTugasModel(id=f"ut_{uuid.uuid4().hex[:12]}", uraian=f"Menyusun dokumen {i}")
        db.add(ut)
        db.flush()
        db.add(
            TiUraianTugasJabatanModel(
                uraian_tugas_id=ut.id, kode=f"P2{uuid.uuid4().hex[:12]}", jabatan_id=jabatan_id,
                unit=unit, urutan=i + 1, tugas_pokok_id=tp.id, std_va_type="VA-Core",
            )
        )  # fmt: skip
        ids.append(ut.id)
    db.flush()
    return ids


def _ajukan(c, jabatan_id: str, badan: dict[str, Any] | None = None):
    return c.post(f"{URL}/{jabatan_id}/normalisasi-ai", json=_BADAN if badan is None else badan)


def _hitung(db: Session, model: Any) -> int:
    return db.scalar(select(func.count()).select_from(model)) or 0


# --- positif -------------------------------------------------------------------------------


def test_positif_202_sasaran_jabatan_40_karakter_dan_sumber_hanya_katalog_jabatan(
    app, client_as, db_session, p02
):
    jid = _jabatan(db_session)
    assert len(jid) == 40
    ut_ids = _uraian(db_session, jid, 3)
    lain = _jabatan(db_session)
    _uraian(db_session, lain, 2)
    _atur(app)
    r = _ajukan(_tim(client_as), jid)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["fungsi"] == "P02" and body["sasaran_jenis"] == "JABATAN"
    assert body["sasaran_id"] == jid
    rec = db_session.get(AiUsulanModel, body["id"])
    db_session.refresh(rec)
    assert rec.sasaran_id == jid and rec.sasaran_jenis == "JABATAN"
    assert rec.sumber_ids == [f"uraian:{u}" for u in ut_ids]
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.fungsi == "P02" and run.status_qa == "MENUNGGU"
    kode_jabatan = db_session.get(JabatanModel, jid).kode
    harapan = {"jabatan_kode": kode_jabatan, "unit": None, "periode": "2026/27"}
    assert run.masukan["parameter"] == harapan
    for s in run.masukan["sumber"]:
        assert s["jenis"] == "KATALOG_TI"
        assert s["source_hash"] == hashlib.sha256(s["teks"].encode()).hexdigest()
        kunci = {b.split(":", 1)[0] for b in s["teks"].splitlines()}
        assert kunci <= set(FIELD_SUMBER_KATALOG_TI)
        assert jid not in s["teks"]


def test_unit_mempersempit_baris_katalog(app, client_as, db_session, p02):
    jid = _jabatan(db_session)
    sd = _uraian(db_session, jid, 2, unit="SD")
    _uraian(db_session, jid, 2, unit="SMP")
    _atur(app)
    r = _ajukan(_tim(client_as), jid, {"periode": "2026-27", "unit": "SD"})
    assert r.status_code == 202, r.text
    rec = db_session.get(AiUsulanModel, r.json()["id"])
    assert rec.sumber_ids == [f"uraian:{u}" for u in sd]


def test_dokumen_pendukung_ikut_dengan_jenisnya_sendiri(app, client_as, db_session, p02):
    jid = _jabatan(db_session)
    ut = _uraian(db_session, jid, 1)
    _atur(app)
    c = _tim(client_as)
    badan = {
        "judul": "j", "jenis": "SINTETIS", "versi": "v1", "periode": "2026-27",
        "teks": "Pedoman fiktif penyusunan RPP.", "izin_ai": True, "izin_catatan": "uji",
    }  # fmt: skip
    sid = c.post(SUMBER, json=badan).json()["id"]
    r = _ajukan(c, jid, {"periode": "2026/27", "sumber_dokumen_ids": [sid, sid]})
    assert r.status_code == 202, r.text
    rec = db_session.get(AiUsulanModel, r.json()["id"])
    assert rec.sumber_ids == [f"uraian:{ut[0]}", sid]
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert [s["jenis"] for s in run.masukan["sumber"]] == ["KATALOG_TI", "SINTETIS"]


def test_jenis_katalog_ti_tidak_diizinkan_bawaan_diblokir_tanpa_model(
    app, client_as, db_session, p02
):
    jid = _jabatan(db_session)
    _uraian(db_session, jid, 1)
    _atur(app, ai_jenis_sumber_diizinkan=["SINTETIS"])
    r = _ajukan(_tim(client_as), jid)
    assert r.status_code == 202, r.text
    run = db_session.get(AiRunModel, db_session.get(AiUsulanModel, r.json()["id"]).ai_run_id)
    assert run.status_qa == "DIBLOKIR" and run.kode_qa == ["JENIS_DITOLAK"]


# --- negatif -------------------------------------------------------------------------------


def test_settings_bawaan_409_tanpa_baris(app, client_as, db_session):
    jid = _jabatan(db_session)
    _uraian(db_session, jid, 1)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    r = _ajukan(_tim(client_as), jid)
    assert r.status_code == 409, r.text
    assert _hitung(db_session, AiUsulanModel) == 0


def test_fungsi_tak_terdaftar_409_fungsi_belum_aktif(app, client_as, db_session):
    jid = _jabatan(db_session)
    _uraian(db_session, jid, 1)
    _atur(app)
    r = _ajukan(_tim(client_as), jid)
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "fungsi_belum_aktif"
    assert _hitung(db_session, AiUsulanModel) == 0


def test_jabatan_tak_ada_404(app, client_as, db_session, p02):
    _atur(app)
    assert _ajukan(_tim(client_as), "jbt_tidak_ada").status_code == 404


def test_sumber_dokumen_tak_ada_404(app, client_as, db_session, p02):
    jid = _jabatan(db_session)
    _uraian(db_session, jid, 1)
    _atur(app)
    r = _ajukan(_tim(client_as), jid, {"periode": "2026/27", "sumber_dokumen_ids": ["tak-ada"]})
    assert r.status_code == 404, r.text


def test_tanpa_uraian_422(app, client_as, db_session, p02):
    jid = _jabatan(db_session)
    _atur(app)
    r = _ajukan(_tim(client_as), jid)
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "TANPA_URAIAN"
    assert _hitung(db_session, AiUsulanModel) == 0


def test_81_uraian_422_terlalu_banyak_80_lolos(app, client_as, db_session, p02):
    jid = _jabatan(db_session)
    _uraian(db_session, jid, 81)
    _atur(app)
    c = _tim(client_as)
    r = _ajukan(c, jid)
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "URAIAN_TERLALU_BANYAK"
    pas = _jabatan(db_session)
    _uraian(db_session, pas, 80)
    assert _ajukan(c, pas).status_code == 202


def test_bukan_tim_kajian_403(app, client_as, db_session, p02):
    jid = _jabatan(db_session)
    _uraian(db_session, jid, 1)
    _atur(app)
    r = _ajukan(client_as("admin-1", groups=["admin"]), jid)
    assert r.status_code == 403


def test_badan_tidak_sah_422(app, client_as, db_session, p02):
    jid = _jabatan(db_session)
    _uraian(db_session, jid, 1)
    _atur(app)
    c = _tim(client_as)
    for badan in (
        {},
        {"periode": "2026/27 ganjil"},
        {"periode": "2026/27", "unit": "S D"},
        {"periode": "2026/27", "sumber_dokumen_ids": [f"s{i}" for i in range(6)]},
        {"periode": "2026/27", "catatan": "teks bebas"},
    ):
        assert _ajukan(c, jid, badan).status_code == 422, badan


# --- helper rangkaian usulan ---------------------------------------------------------------


def _usulan(db: Session, isi: dict[str, Any] | None = None) -> AiUsulanModel:
    run_id = str(uuid.uuid4())
    db.add(
        AiRunModel(
            id=run_id, fungsi="P02", prompt_version="v1", prompt_hash="a" * 64,
            model_diminta="model-uji", protocol_id="uji", input_snapshot_id="b" * 64,
            sumber=[], masukan={}, keluaran={}, status_qa="LOLOS", kode_qa=[],
        )
    )  # fmt: skip
    db.flush()
    rec = AiUsulanModel(
        id=str(uuid.uuid4()), fungsi="P02", sasaran_jenis="JABATAN", sasaran_id="jbt_x",
        job_id=str(uuid.uuid4()), ai_run_id=run_id, sumber_ids=["uraian:x"],
        diminta_oleh="tim-1", diserap_at=_DASAR, hasil_serap="USULAN_DIBUAT",
        isi={"z": 1, "a": "é"} if isi is None else isi,
    )  # fmt: skip
    db.add(rec)
    db.flush()
    return rec


def _putus(db: Session, usulan_id: str, putusan: str, menit: int, **kw: Any) -> None:
    db.add(
        AiUsulanPutusanModel(
            id=str(uuid.uuid4()), usulan_id=usulan_id, putusan=putusan, actor_key="r",
            created_at=_DASAR + timedelta(minutes=menit), **kw,
        )
    )  # fmt: skip
    db.flush()


def _svc(db: Session) -> SqlAiUsulanService:
    return SqlAiUsulanService(db, Settings(_env_file=None), gateway=None)  # type: ignore[arg-type]


def test_rangkaian_approve_memakai_json_kanonik_isi(db_session):
    rec = _usulan(db_session)
    _putus(db_session, rec.id, "APPROVE", 1)
    s = _svc(db_session).sumber_dari_usulan(rec.id)
    assert s.source_id == f"usulan:{rec.id}" and s.jenis == "USULAN_AI"
    assert s.teks == json.dumps(rec.isi, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert s.teks == '{"a":"é","z":1}'
    assert s.source_hash == hashlib.sha256(s.teks.encode()).hexdigest()


def test_rangkaian_revise_memakai_teks_koreksi(db_session):
    rec = _usulan(db_session)
    _putus(db_session, rec.id, "APPROVE", 1)
    _putus(db_session, rec.id, "REVISE", 2, tingkat_koreksi="MINOR", teks_koreksi="Teks koreksi.")
    assert _svc(db_session).sumber_dari_usulan(rec.id).teks == "Teks koreksi."


@pytest.mark.parametrize("putusan", [None, "REJECT"])
def test_rangkaian_tanpa_putusan_atau_reject_409_usulan_belum_diterima(db_session, putusan):
    rec = _usulan(db_session)
    if putusan:
        _putus(db_session, rec.id, "APPROVE", 1)
        _putus(db_session, rec.id, putusan, 2, tingkat_koreksi="MAJOR", catatan="Tidak berdasar.")
    with pytest.raises(UsulanBelumDiterimaError) as exc:
        _svc(db_session).sumber_dari_usulan(rec.id)
    assert exc.value.status_code == 409
    assert exc.value.error_code == "USULAN_BELUM_DITERIMA"


def test_rangkaian_usulan_tak_ada_404(db_session):
    with pytest.raises(NotFoundError):
        _svc(db_session).sumber_dari_usulan(str(uuid.uuid4()))
