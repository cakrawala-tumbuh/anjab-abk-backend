"""Tes rute `POST /api/v1/riset/protokol/{id}/sintesis-ai` (P08).

Klien model sungguhan tidak pernah dibuat; data sintetis; tanpa jaringan. Gerbang protokol
terkunci dan statistik terverifikasi dicek sebelum run dibuat: pengajuan yang gagal tidak
meninggalkan `ai_usulan` maupun `ai_run`.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from anjab_abk_backend.ai import klien as modul_klien
from anjab_abk_backend.ai.fungsi_p08 import FUNGSI_P08
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.api.v1.riset_sintesis_ai import MAKS_SUMBER_P08
from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.models import (
    AiRunModel,
    AiUsulanModel,
    RisetKasusNegatifModel,
    RisetProtokolModel,
    RisetStatistikModel,
)

URL = "/api/v1/riset/protokol"
pytestmark = pytest.mark.usefixtures("penyedia_api")

_HIDUP = {
    "_env_file": None,
    "feature_ai_narrative_draft": True,
    "ai_jenis_sumber_diizinkan": ["RISET"],
}


@pytest.fixture(autouse=True)
def _klien_dilarang(monkeypatch):
    """Konstruksi klien model asli apa pun menggagalkan tes (nol panggilan jaringan)."""

    def _larang(*_a: Any, **_k: Any) -> None:
        raise AssertionError("klien model tidak boleh dibuat")

    monkeypatch.setattr(modul_klien.AnthropicKlienModel, "__init__", _larang)
    monkeypatch.setattr(modul_klien.ClaudeCliKlienModel, "__init__", _larang)


@pytest.fixture
def p08(monkeypatch):
    """Daftarkan P08 pada registri (dipulihkan otomatis)."""
    monkeypatch.setitem(FUNGSI_TERDAFTAR, "P08", FUNGSI_P08)


def _atur(app, **ubah: Any) -> Settings:
    cfg = Settings(**{**_HIDUP, **ubah})
    app.dependency_overrides[get_settings] = lambda: cfg
    return cfg


def _tim(client_as):
    return client_as("tim-p08", groups=["tim-kajian"])


def _protokol(db: Session, *, terkunci: bool = True) -> RisetProtokolModel:
    rec = RisetProtokolModel(
        id=str(uuid.uuid4()), kode=f"P08-{uuid.uuid4().hex[:8]}", versi=1, judul="Protokol uji",
        isi="Metode: Cronbach alpha per sub-skala.",
        status="TERKUNCI" if terkunci else "DRAF",
        isi_hash="a" * 64 if terkunci else None, dibuat_oleh="tim-a",
        dikunci_oleh="tim-a" if terkunci else None,
    )  # fmt: skip
    db.add(rec)
    db.flush()  # FK telanjang tanpa relationship(): induk wajib di-flush lebih dulu
    return rec


def _statistik(db: Session, protokol_id: str, status: str, nama: str) -> str:
    sid = str(uuid.uuid4())
    db.add(
        RisetStatistikModel(
            id=sid, protokol_id=protokol_id, nama_analisis=nama,
            keluaran="sub_skala  alpha\nTuntutan   0.81", kode_sumber_ref="analisis/a.py@3f2a9c1",
            status=status, dibuat_oleh="tim-a",
            diverifikasi_oleh="tim-b" if status == "TERVERIFIKASI" else None,
        )
    )  # fmt: skip
    db.flush()
    return sid


def _kasus_negatif(db: Session, protokol_id: str) -> str:
    kid = str(uuid.uuid4())
    db.add(
        RisetKasusNegatifModel(
            id=kid, protokol_id=protokol_id, ringkasan="Satu sekolah alpha di bawah 0.6",
            alasan_negatif="Berlawanan dengan dugaan", dibuat_oleh="tim-a",
        )
    )  # fmt: skip
    db.flush()
    return kid


def _ajukan(c, protokol_id: str, periode: str = "2026/27"):
    return c.post(f"{URL}/{protokol_id}/sintesis-ai", json={"periode": periode})


def _hitung(db: Session, model: Any) -> int:
    stmt = select(func.count()).select_from(model).where(model.fungsi == "P08")
    return db.scalar(stmt) or 0


def _assert_409(r, db: Session, kode: str) -> None:
    assert r.status_code == 409, r.text
    assert r.json()["error"] == kode
    assert _hitung(db, AiUsulanModel) == 0 and _hitung(db, AiRunModel) == 0


# --- positif -------------------------------------------------------------------------------


def test_positif_202_sumber_tanpa_statistik_draf(app, client_as, db_session, p08):
    prot = _protokol(db_session)
    sid = _statistik(db_session, prot.id, "TERVERIFIKASI", "Alpha terverifikasi")
    _statistik(db_session, prot.id, "DRAF", "Alpha-draf-rahasia-q8")
    kid = _kasus_negatif(db_session, prot.id)
    _atur(app)
    r = _ajukan(_tim(client_as), prot.id)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["fungsi"] == "P08" and body["sasaran_jenis"] == "PROTOKOL_RISET"
    assert body["sasaran_id"] == prot.id
    rec = db_session.get(AiUsulanModel, body["id"])
    db_session.refresh(rec)
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.fungsi == "P08"
    assert run.masukan["parameter"] == {
        "protokol_kode": prot.kode,
        "protokol_versi": 1,
        "periode": "2026/27",
    }
    sumber = run.masukan["sumber"]
    assert {s["jenis"] for s in sumber} == {"RISET"}
    ids = [s["source_id"] for s in sumber]
    assert ids[0] == f"protokol:{prot.id}"
    assert [i for i in ids if i.startswith("statistik:")] == [f"statistik:{sid}"]
    assert [i for i in ids if i.startswith("kasus-negatif:")] == [f"kasus-negatif:{kid}"]
    assert all(i.split(":", 1)[0] in {"protokol", "statistik", "kasus-negatif", "versi-metode"}
               for i in ids)  # fmt: skip
    semua = "".join(s["teks"] for s in sumber)
    assert "Alpha-draf-rahasia-q8" not in semua
    assert "tim-a" not in semua and "tim-b" not in semua
    teks_prot = sumber[0]["teks"]
    assert f"kode: {prot.kode}" in teks_prot and "isi_hash: " + "a" * 64 in teks_prot


# --- negatif -------------------------------------------------------------------------------


def test_protokol_draf_409_protokol_belum_terkunci(app, client_as, db_session, p08):
    prot = _protokol(db_session, terkunci=False)
    _atur(app)
    _assert_409(_ajukan(_tim(client_as), prot.id), db_session, "PROTOKOL_BELUM_TERKUNCI")


def test_tanpa_statistik_terverifikasi_409(app, client_as, db_session, p08):
    prot = _protokol(db_session)
    _statistik(db_session, prot.id, "DRAF", "Alpha draf")
    _kasus_negatif(db_session, prot.id)
    _atur(app)
    _assert_409(_ajukan(_tim(client_as), prot.id), db_session, "STATISTIK_TERVERIFIKASI_KOSONG")


def test_fungsi_tak_terdaftar_409_fungsi_belum_aktif(app, client_as, db_session):
    prot = _protokol(db_session)
    _statistik(db_session, prot.id, "TERVERIFIKASI", "Alpha")
    _atur(app)
    _assert_409(_ajukan(_tim(client_as), prot.id), db_session, "fungsi_belum_aktif")


def test_fungsi_tak_terdaftar_dicek_sebelum_status_protokol(app, client_as, db_session):
    prot = _protokol(db_session, terkunci=False)
    _atur(app)
    _assert_409(_ajukan(_tim(client_as), prot.id), db_session, "fungsi_belum_aktif")


def test_settings_bawaan_flag_mati_409_feature_disabled(app, client_as, db_session, p08):
    prot = _protokol(db_session)
    _statistik(db_session, prot.id, "TERVERIFIKASI", "Alpha")
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    r = _ajukan(_tim(client_as), prot.id)
    assert r.status_code == 409 and r.json()["error"] == "feature_disabled"


def test_protokol_tak_ada_404(app, client_as, db_session, p08):
    _atur(app)
    assert _ajukan(_tim(client_as), str(uuid.uuid4())).status_code == 404


def test_sumber_terlalu_banyak_422(app, client_as, db_session, p08):
    prot = _protokol(db_session)
    for i in range(MAKS_SUMBER_P08):
        _statistik(db_session, prot.id, "TERVERIFIKASI", f"Analisis {i}")
    _atur(app)
    r = _ajukan(_tim(client_as), prot.id)
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "SUMBER_TERLALU_BANYAK"
    assert _hitung(db_session, AiUsulanModel) == 0


def test_bukan_tim_kajian_403(app, client_as, db_session, p08):
    prot = _protokol(db_session)
    _atur(app)
    assert _ajukan(client_as("admin-1", groups=["admin"]), prot.id).status_code == 403


def test_badan_tidak_sah_422(app, client_as, db_session, p08):
    prot = _protokol(db_session)
    _statistik(db_session, prot.id, "TERVERIFIKASI", "Alpha")
    _atur(app)
    c = _tim(client_as)
    for badan in ({}, {"periode": "2026/27", "catatan": "bebas"}, {"periode": "x y"}):
        assert c.post(f"{URL}/{prot.id}/sintesis-ai", json=badan).status_code == 422, badan
