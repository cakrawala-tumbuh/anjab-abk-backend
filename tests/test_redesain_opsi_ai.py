"""Tes rute `POST /api/v1/redesain/masalah/{id}/opsi-ai` (P06) dan gerbang F4 `periksa_syarat_f4`.

Klien model sungguhan tidak pernah dibuat; data sintetis; tanpa jaringan. Gerbang F4 dicek
sebelum run dibuat: masalah yang gagal tidak meninggalkan `ai_usulan` maupun `ai_run`.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from anjab_abk_backend.ai import klien as modul_klien
from anjab_abk_backend.ai.fungsi_p06 import FUNGSI_P06
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.syarat_f4 import (
    KODE_AUDIT_BUKTI_BELUM_MINIMAL,
    KODE_BUKTI_DIPERSELISIHKAN,
    KODE_KLAIM_BELUM_TERVALIDASI,
    VERSI_SYARAT_F4,
    periksa_syarat_f4,
)
from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.models import (
    AiRunModel,
    AiUsulanModel,
    RedesainAlternatifModel,
    RedesainBuktiModel,
    RedesainKonteksModel,
    RedesainLangkahModel,
    RedesainMasalahModel,
    RedesainPenilaianModel,
    RedesainProsesModel,
    SekolahModel,
)

URL = "/api/v1/redesain/masalah"
pytestmark = pytest.mark.usefixtures("penyedia_api")

_HIDUP = {
    "_env_file": None,
    "feature_ai_narrative_draft": True,
    "ai_jenis_sumber_diizinkan": ["REDESAIN"],
}
_SESUAI = "Diperiksa sesuai klaim"
_DIPERKUAT = "Diperkuat untuk klaim"


@pytest.fixture(autouse=True)
def _klien_dilarang(monkeypatch):
    """Konstruksi klien model asli apa pun menggagalkan tes (nol panggilan jaringan)."""

    def _larang(*_a: Any, **_k: Any) -> None:
        raise AssertionError("klien model tidak boleh dibuat")

    monkeypatch.setattr(modul_klien.AnthropicKlienModel, "__init__", _larang)
    monkeypatch.setattr(modul_klien.ClaudeCliKlienModel, "__init__", _larang)


@pytest.fixture
def p06(monkeypatch):
    """Daftarkan P06 pada registri (dipulihkan otomatis)."""
    monkeypatch.setitem(FUNGSI_TERDAFTAR, "P06", FUNGSI_P06)


def _atur(app, **ubah: Any) -> Settings:
    cfg = Settings(**{**_HIDUP, **ubah})
    app.dependency_overrides[get_settings] = lambda: cfg
    return cfg


def _tim(client_as):
    return client_as("tim-p06", groups=["tim-kajian"])


def _hex() -> str:
    return uuid.uuid4().hex[:8]


def _masalah(db: Session) -> str:
    konteks = db.scalars(
        select(RedesainKonteksModel.id).where(RedesainKonteksModel.kode == "K-01")
    ).one()
    mid = str(uuid.uuid4())
    db.add(
        RedesainMasalahModel(
            id=mid, kode=f"M-T{_hex()}", konteks_id=konteks, periode_acuan="2026/27",
            rumusan_hipotesis="Rekap nilai terlambat", sumber_awal_keterbatasan="Catatan rapat",
            status_awal="Dugaan", gelombang="G1",
        )
    )  # fmt: skip
    db.flush()
    return mid


def _proses(db: Session, masalah_id: str) -> str:
    sid = f"skl_{_hex()}"
    db.add(SekolahModel(id=sid, nama=f"SD Uji {sid}", jenjang_pendidikan_id="jp_dummy"))
    db.flush()  # FK telanjang tanpa relationship(): induk wajib di-flush lebih dulu
    pid = str(uuid.uuid4())
    db.add(
        RedesainProsesModel(
            id=pid, kode=f"P-{_hex()}", masalah_id=masalah_id, sekolah_id=sid,
            periode="2026/27", nama_proses="Penyusunan rekap",
        )
    )  # fmt: skip
    db.flush()
    db.add(
        RedesainLangkahModel(
            id=str(uuid.uuid4()), proses_id=pid, kode=f"L-{_hex()}", urutan=1, tahap="Tahap 1",
            pemicu_input="Akhir semester", pelaksana="Guru", pekerjaan_sistem="Mengisi",
            keluaran_penerima="Lembar nilai", status_langkah="Dicatat",
        )
    )  # fmt: skip
    db.flush()
    return pid


def _penilaian(db: Session, masalah_id: str, status_bukti: str) -> None:
    db.add(
        RedesainPenilaianModel(
            id=str(uuid.uuid4()), masalah_id=masalah_id, status_bukti=status_bukti,
            gap_material="Tidak", indikasi_kritis="Tidak terlihat", versi_aturan_triase="v1",
        )
    )  # fmt: skip
    db.flush()


def _bukti(db: Session, masalah_id: str, *status: str) -> None:
    for st in status:
        db.add(
            RedesainBuktiModel(
                id=str(uuid.uuid4()), kode=f"B-{_hex()}", masalah_id=masalah_id,
                unit_periode="SD 2026/27", jenis="Keluaran/dokumen", independen="Ya",
                klaim_didukung="Format berbeda", tanggal_versi_lokasi="Folder kurikulum",
                status_pemeriksaan=st,
            )
        )  # fmt: skip
    db.flush()


def _alternatif(db: Session, masalah_id: str) -> str:
    aid = str(uuid.uuid4())
    db.add(
        RedesainAlternatifModel(
            id=aid, kode=f"U-{_hex()}", masalah_id=masalah_id, opsi="Sederhanakan",
            alur_kini_vs_usulan="Tiga format menjadi satu", komitmen_penerima="Belum dibahas",
            risiko_layanan="Penyesuaian lembar lama", keputusan="Keputusan-rahasia-q8",
            status_telaah="Siap telaah",
        )
    )  # fmt: skip
    db.flush()
    return aid


def _lolos_f4(db: Session) -> str:
    mid = _masalah(db)
    _proses(db, mid)
    _penilaian(db, mid, _DIPERKUAT)
    _bukti(db, mid, _SESUAI)
    return mid


def _ajukan(c, masalah_id: str, periode: str = "2026/27"):
    return c.post(f"{URL}/{masalah_id}/opsi-ai", json={"periode": periode})


def _hitung(db: Session, model: Any) -> int:
    stmt = select(func.count()).select_from(model).where(model.fungsi == "P06")
    return db.scalar(stmt) or 0


def _assert_f4_409(r, db: Session, kode: list[str]) -> None:
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "SYARAT_F4_BELUM_TERPENUHI"
    assert [d["code"] for d in body["details"]] == kode
    assert {tuple(d["loc"]) for d in body["details"]} == {("alasan",)}
    assert _hitung(db, AiUsulanModel) == 0 and _hitung(db, AiRunModel) == 0


# --- positif -------------------------------------------------------------------------------


def test_positif_202_lolos_f4_sumber_memuat_alternatif(app, client_as, db_session, p06):
    mid = _lolos_f4(db_session)
    aid = _alternatif(db_session, mid)
    _atur(app)
    r = _ajukan(_tim(client_as), mid)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["fungsi"] == "P06" and body["sasaran_jenis"] == "REDESAIN_MASALAH"
    assert body["sasaran_id"] == mid
    rec = db_session.get(AiUsulanModel, body["id"])
    db_session.refresh(rec)
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.fungsi == "P06"
    assert run.masukan["parameter"] == {
        "masalah_id": mid,
        "periode": "2026/27",
        "versi_syarat_f4": VERSI_SYARAT_F4,
        "source_verified_quantities": [],
    }
    sumber = run.masukan["sumber"]
    assert {s["jenis"] for s in sumber} == {"REDESAIN"}
    ids = [s["source_id"] for s in sumber]
    assert ids[0] == f"masalah:{mid}" and ids[-1] == f"alternatif:{aid}"
    teks_alt = sumber[-1]["teks"]
    assert "opsi: Sederhanakan" in teks_alt and "komitmen_penerima: Belum dibahas" in teks_alt
    assert "Keputusan-rahasia-q8" not in teks_alt and "Siap telaah" not in teks_alt
    assert "jam_per_minggu" not in "".join(s["teks"] for s in sumber)


# --- negatif: gerbang F4 (satu per syarat) ---------------------------------------------------


def test_penilaian_hipotesis_klaim_belum_tervalidasi(app, client_as, db_session, p06):
    mid = _masalah(db_session)
    _penilaian(db_session, mid, "Hipotesis")
    _bukti(db_session, mid, _SESUAI)
    _atur(app)
    _assert_f4_409(_ajukan(_tim(client_as), mid), db_session, [KODE_KLAIM_BELUM_TERVALIDASI])


def test_tanpa_penilaian_klaim_belum_tervalidasi(app, client_as, db_session, p06):
    mid = _masalah(db_session)
    _bukti(db_session, mid, _SESUAI)
    _atur(app)
    _assert_f4_409(_ajukan(_tim(client_as), mid), db_session, [KODE_KLAIM_BELUM_TERVALIDASI])


def test_semua_bukti_belum_diperiksa_audit_belum_minimal(app, client_as, db_session, p06):
    mid = _masalah(db_session)
    _penilaian(db_session, mid, _DIPERKUAT)
    _bukti(db_session, mid, "Belum diperiksa", "Belum diperiksa")
    _atur(app)
    _assert_f4_409(_ajukan(_tim(client_as), mid), db_session, [KODE_AUDIT_BUKTI_BELUM_MINIMAL])


def test_ada_bukti_diperselisihkan(app, client_as, db_session, p06):
    mid = _masalah(db_session)
    _penilaian(db_session, mid, _DIPERKUAT)
    _bukti(db_session, mid, _SESUAI, "Diperselisihkan")
    _atur(app)
    _assert_f4_409(_ajukan(_tim(client_as), mid), db_session, [KODE_BUKTI_DIPERSELISIHKAN])


def test_periksa_syarat_f4_menggabungkan_semua_kode(db_session):
    mid = _masalah(db_session)
    assert periksa_syarat_f4(db_session, mid) == [
        KODE_KLAIM_BELUM_TERVALIDASI,
        KODE_AUDIT_BUKTI_BELUM_MINIMAL,
    ]
    _bukti(db_session, mid, "Diperselisihkan")
    assert periksa_syarat_f4(db_session, mid)[-1] == KODE_BUKTI_DIPERSELISIHKAN
    assert periksa_syarat_f4(db_session, _lolos_f4(db_session)) == []


# --- negatif: lain -------------------------------------------------------------------------


def test_fungsi_tak_terdaftar_409_fungsi_belum_aktif(app, client_as, db_session):
    mid = _lolos_f4(db_session)
    _atur(app)
    r = _ajukan(_tim(client_as), mid)
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "fungsi_belum_aktif"
    assert _hitung(db_session, AiUsulanModel) == 0


def test_masalah_tak_ada_404(app, client_as, db_session, p06):
    _atur(app)
    assert _ajukan(_tim(client_as), str(uuid.uuid4())).status_code == 404


def test_bukan_tim_kajian_403(app, client_as, db_session, p06):
    mid = _lolos_f4(db_session)
    _atur(app)
    assert _ajukan(client_as("admin-1", groups=["admin"]), mid).status_code == 403


def test_badan_tidak_sah_422(app, client_as, db_session, p06):
    mid = _lolos_f4(db_session)
    _atur(app)
    c = _tim(client_as)
    for badan in ({}, {"periode": "2026/27", "jam_per_minggu": 5}, {"periode": "x y"}):
        r = c.post(f"{URL}/{mid}/opsi-ai", json=badan)
        assert r.status_code == 422, badan
