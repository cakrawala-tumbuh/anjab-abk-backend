"""Tes rute `POST /api/v1/redesain/konteks/usulan-ai` (P11) dan penyerapannya.

Klien model sungguhan tidak pernah dibuat; data sintetis; tanpa jaringan. Konteks hasil seed
dinonaktifkan di awal tiap tes (di dalam transaksi tes) agar jumlah sumber pasti. Pengajuan yang
gagal tidak meninggalkan `ai_usulan` maupun `ai_run`.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from anjab_abk_backend.ai import klien as modul_klien
from anjab_abk_backend.ai.fungsi_p11 import FUNGSI_P11
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.penyerap_usulan import serap_usulan
from anjab_abk_backend.api.v1.redesain_konteks_usulan_ai import MAKS_SUMBER_P11
from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.models import (
    AiRunModel,
    AiUsulanModel,
    RedesainKonteksModel,
    RedesainMasalahModel,
    SekolahModel,
)
from anjab_abk_backend.schemas.ai_run import StatusQaAi
from anjab_abk_backend.services.ai_run_sql import SqlAiRunService

URL = "/api/v1/redesain/konteks/usulan-ai"
SUMBER = "/api/v1/narasi/sumber"
pytestmark = pytest.mark.usefixtures("penyedia_api")

_HIDUP = {
    "_env_file": None,
    "feature_ai_narrative_draft": True,
    "ai_jenis_sumber_diizinkan": ["REDESAIN", "SINTETIS"],
    "ai_simpan_masukan": True,
}
_PIC = "ORG-P11-9917"
_KET_SEKOLAH = "Sekolah Fiktif Rahasia P11"


@pytest.fixture(autouse=True)
def _klien_dilarang(monkeypatch):
    """Konstruksi klien model asli apa pun menggagalkan tes (nol panggilan jaringan)."""

    def _larang(*_a: Any, **_k: Any) -> None:
        raise AssertionError("klien model tidak boleh dibuat")

    monkeypatch.setattr(modul_klien.AnthropicKlienModel, "__init__", _larang)
    monkeypatch.setattr(modul_klien.ClaudeCliKlienModel, "__init__", _larang)


@pytest.fixture(autouse=True)
def _seed_nonaktif(db_session: Session):
    """Nonaktifkan konteks hasil seed (masalahnya ikut tersaring); dibatalkan rollback tes."""
    db_session.execute(update(RedesainKonteksModel).values(aktif=False))
    db_session.flush()


@pytest.fixture
def p11(monkeypatch):
    """Daftarkan P11 pada registri (dipulihkan otomatis)."""
    monkeypatch.setitem(FUNGSI_TERDAFTAR, "P11", FUNGSI_P11)


def _atur(app, **ubah: Any) -> Settings:
    cfg = Settings(**{**_HIDUP, **ubah})
    app.dependency_overrides[get_settings] = lambda: cfg
    return cfg


def _tim(client_as):
    return client_as("tim-p11", groups=["tim-kajian"])


def _konteks(db: Session, kode: str, *, aktif: bool = True) -> RedesainKonteksModel:
    rec = RedesainKonteksModel(
        id=str(uuid.uuid4()), kode=kode, tema=f"Tema {kode}", gelombang="G1",
        ruang_dugaan=f"Dugaan rekap berulang {kode}", sumber_draft="Catatan rapat sintetis",
        batas_pemeriksaan="Jam kerja belum diukur", aktif=aktif,
    )  # fmt: skip
    db.add(rec)
    db.flush()
    return rec


def _masalah(db: Session, konteks: RedesainKonteksModel, urut: int) -> RedesainMasalahModel:
    sekolah = db.scalars(select(SekolahModel).limit(1)).first()
    rec = RedesainMasalahModel(
        id=str(uuid.uuid4()), kode=f"MP11-{konteks.kode}-{urut}", konteks_id=konteks.id,
        sekolah_id=sekolah.id if sekolah else None, keterangan_sekolah=_KET_SEKOLAH,
        periode_acuan="2026/27", rumusan_hipotesis="Wali kelas menyamakan format nilai",
        sumber_awal_keterbatasan="Satu diskusi", status_awal="Hipotesis", gelombang="G1",
        pic_kode_orang=_PIC,
    )  # fmt: skip
    db.add(rec)
    db.flush()
    return rec


def _hitung(db: Session, model: Any) -> int:
    stmt = select(func.count()).select_from(model).where(model.fungsi == "P11")
    return db.scalar(stmt) or 0


def _assert_gagal(r, db: Session, status: int, kode: str) -> None:
    assert r.status_code == status, r.text
    assert r.json()["error"] == kode
    assert _hitung(db, AiUsulanModel) == 0 and _hitung(db, AiRunModel) == 0


def _katalog(db: Session) -> tuple[list[RedesainKonteksModel], list[RedesainMasalahModel]]:
    k = [_konteks(db, f"KP{i}") for i in (1, 2, 3)]
    return k, [_masalah(db, k[0], 1), _masalah(db, k[1], 1)]


# --- positif -------------------------------------------------------------------------------


def test_positif_202_sumber_konteks_dan_masalah_berjenis_redesain(app, client_as, db_session, p11):
    konteks, masalah = _katalog(db_session)
    _konteks(db_session, "KP9", aktif=False)
    _atur(app)
    r = _tim(client_as).post(URL, json={})
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["fungsi"] == "P11" and body["sasaran_jenis"] == "REDESAIN_KONTEKS"
    assert body["sasaran_id"] == "KATALOG"
    rec = db_session.get(AiUsulanModel, body["id"])
    db_session.refresh(rec)
    assert rec.konteks_server == {"jumlah_kandidat": 3, "kode_konteks_ada": ["KP1", "KP2", "KP3"]}
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.fungsi == "P11"
    assert run.masukan["parameter"] == {
        "jumlah_kandidat": 3,
        "sertakan_masalah": True,
        "kode_konteks_ada": ["KP1", "KP2", "KP3"],
    }
    sumber = run.masukan["sumber"]
    assert {s["jenis"] for s in sumber} == {"REDESAIN"}
    assert [s["source_id"] for s in sumber] == [
        *(f"konteks:{k.id}" for k in konteks),
        *(f"masalah:{m.id}" for m in masalah),
    ]
    teks_masalah = [s["teks"] for s in sumber if s["source_id"].startswith("masalah:")]
    assert all("konteks_kode: KP" in t for t in teks_masalah)
    for t in teks_masalah:
        assert _PIC not in t and _KET_SEKOLAH not in t
    assert "batas_pemeriksaan: Jam kerja belum diukur" in sumber[0]["teks"]


def test_sertakan_masalah_false_tanpa_sumber_masalah(app, client_as, db_session, p11):
    konteks, _ = _katalog(db_session)
    _atur(app)
    r = _tim(client_as).post(URL, json={"sertakan_masalah": False, "jumlah_kandidat": 2})
    assert r.status_code == 202, r.text
    rec = db_session.get(AiUsulanModel, r.json()["id"])
    assert rec.sumber_ids == [f"konteks:{k.id}" for k in konteks]
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.masukan["parameter"]["sertakan_masalah"] is False
    assert run.masukan["parameter"]["jumlah_kandidat"] == 2


def test_dokumen_pendukung_ikut_dengan_jenisnya_sendiri(app, client_as, db_session, p11):
    konteks, masalah = _katalog(db_session)
    _atur(app)
    c = _tim(client_as)
    badan = {
        "judul": "j", "jenis": "SINTETIS", "versi": "v1", "periode": "2026-27",
        "teks": "Pedoman fiktif penyusunan rapor.", "izin_ai": True, "izin_catatan": "uji",
    }  # fmt: skip
    sid = c.post(SUMBER, json=badan).json()["id"]
    r = c.post(URL, json={"sumber_dokumen_ids": [sid, sid]})
    assert r.status_code == 202, r.text
    rec = db_session.get(AiUsulanModel, r.json()["id"])
    assert rec.sumber_ids[-1] == sid and len(rec.sumber_ids) == 6
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert [s["jenis"] for s in run.masukan["sumber"]] == ["REDESAIN"] * 5 + ["SINTETIS"]


# --- negatif -------------------------------------------------------------------------------


def test_fungsi_tak_terdaftar_409(app, client_as, db_session):
    _katalog(db_session)
    _atur(app)
    _assert_gagal(_tim(client_as).post(URL, json={}), db_session, 409, "fungsi_belum_aktif")


def test_tanpa_konteks_aktif_422(app, client_as, db_session, p11):
    _konteks(db_session, "KP9", aktif=False)
    _atur(app)
    _assert_gagal(_tim(client_as).post(URL, json={}), db_session, 422, "TANPA_KONTEKS")


def test_dokumen_tak_ada_404(app, client_as, db_session, p11):
    _katalog(db_session)
    _atur(app)
    r = _tim(client_as).post(URL, json={"sumber_dokumen_ids": ["tak-ada"]})
    assert r.status_code == 404, r.text
    assert _hitung(db_session, AiUsulanModel) == 0


def test_dokumen_tanpa_izin_ai_409(app, client_as, db_session, p11):
    _katalog(db_session)
    _atur(app)
    c = _tim(client_as)
    badan = {
        "judul": "j", "jenis": "SINTETIS", "versi": "v1", "periode": "2026-27",
        "teks": "Pedoman fiktif.", "izin_ai": False,
    }  # fmt: skip
    sid = c.post(SUMBER, json=badan).json()["id"]
    _assert_gagal(
        c.post(URL, json={"sumber_dokumen_ids": [sid]}), db_session, 409, "izin_sumber_tidak_ada"
    )


def test_settings_bawaan_flag_mati_409_feature_disabled(app, client_as, db_session, p11):
    _katalog(db_session)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    _assert_gagal(_tim(client_as).post(URL, json={}), db_session, 409, "feature_disabled")


def test_sumber_terlalu_banyak_422(app, client_as, db_session, p11):
    for i in range(MAKS_SUMBER_P11 + 1):
        _konteks(db_session, f"KB{i:02d}")
    _atur(app)
    _assert_gagal(_tim(client_as).post(URL, json={}), db_session, 422, "SUMBER_TERLALU_BANYAK")


def test_bukan_tim_kajian_403(app, client_as, db_session, p11):
    _katalog(db_session)
    _atur(app)
    assert client_as("admin-1", groups=["admin"]).post(URL, json={}).status_code == 403


def test_badan_tidak_sah_422(app, client_as, db_session, p11):
    _katalog(db_session)
    _atur(app)
    c = _tim(client_as)
    for badan in (
        {"jumlah_kandidat": 0},
        {"jumlah_kandidat": 6},
        {"catatan": "bebas"},
        {"sumber_dokumen_ids": [f"s{i}" for i in range(6)]},
    ):
        assert c.post(URL, json=badan).status_code == 422, badan


def test_rute_konteks_lama_tetap_utuh(app, client_as, db_session):
    k = _konteks(db_session, "KP1")
    r = _tim(client_as).get(f"/api/v1/redesain/konteks/{k.id}")
    assert r.status_code == 200, r.text
    assert r.json()["kode"] == "KP1"


# --- penyerapan ----------------------------------------------------------------------------


def _keluaran(sumber_ids: list[str], kandidat: int, mirip: str | None) -> dict[str, Any]:
    return {
        "status": "AI_DRAFT",
        "source_refs": [{"source_id": s, "source_hash": "a" * 64} for s in sumber_ids],
        "cited_spans": [],
        "confidence_reason": "alasan",
        "unknowns": [],
        "contradictions": [],
        "human_review_required": True,
        "isi": {
            "konteks_candidates": [
                {"tema": "Rekap nilai", "ruang_dugaan": "d", "sumber_draft": "s",
                 "batas_pemeriksaan": "b", "gelombang_saran": "G1", "mirip_kode": mirip,
                 "source_ids": sumber_ids[:1]}
                for _ in range(kandidat)
            ],
            "reviewer_questions": [],
        },
    }  # fmt: skip


def _serap(db: Session, usulan_id: str, keluaran: dict[str, Any]) -> AiUsulanModel:
    rec = db.get(AiUsulanModel, usulan_id)
    SqlAiRunService(db, Settings(**_HIDUP)).tutup(
        rec.ai_run_id, StatusQaAi.LOLOS, [], keluaran, None, None, None, None
    )
    serap_usulan(db, usulan_id)
    db.flush()
    db.expire_all()
    return db.get(AiUsulanModel, usulan_id)


@pytest.mark.parametrize(
    ("kandidat", "mirip", "hasil", "kode"),
    [
        (3, "KP1", "USULAN_DIBUAT", None),
        (4, None, "MANUAL", ["KANDIDAT_BERLEBIH"]),
        (1, "K-99", "MANUAL", ["KODE_KONTEKS_TAK_DIKENAL"]),
    ],
    ids=["sah", "berlebih", "kode_tak_dikenal"],
)
def test_penyerap_memakai_konteks_server_untuk_aturan_isi(
    app, client_as, db_session, p11, kandidat, mirip, hasil, kode
):
    _katalog(db_session)
    _atur(app)
    r = _tim(client_as).post(URL, json={"sertakan_masalah": False})
    assert r.status_code == 202, r.text
    rec = db_session.get(AiUsulanModel, r.json()["id"])
    rec = _serap(db_session, rec.id, _keluaran(list(rec.sumber_ids), kandidat, mirip))
    assert rec.hasil_serap == hasil
    assert rec.kode_serap == kode
    if hasil == "USULAN_DIBUAT":
        assert "konteks_server" not in rec.amplop
        assert len(rec.isi["konteks_candidates"]) == 3
