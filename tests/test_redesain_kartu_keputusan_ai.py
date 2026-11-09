"""Tes rute `POST /api/v1/redesain/masalah/{id}/kartu-keputusan-ai` (P07) dan `konteks_server`.

Klien model sungguhan tidak pernah dibuat; data sintetis; tanpa jaringan. Gerbang F4 + alternatif
dicek sebelum run dibuat: masalah yang gagal tidak meninggalkan `ai_usulan` maupun `ai_run`.
`authorization_state` diisi server dan disimpan di `ai_usulan.konteks_server`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from anjab_abk_backend.ai import klien as modul_klien
from anjab_abk_backend.ai.fungsi_p06 import FUNGSI_P06
from anjab_abk_backend.ai.fungsi_p07 import FUNGSI_P07
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.syarat_f4 import (
    KODE_ALTERNATIF_BELUM_ADA,
    KODE_KLAIM_BELUM_TERVALIDASI,
    VERSI_SYARAT_F4,
    periksa_syarat_p07,
)
from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.models import (
    AiRunModel,
    AiUsulanModel,
    AiUsulanPutusanModel,
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
    "ai_jenis_sumber_diizinkan": ["REDESAIN", "USULAN_AI"],
}
_DASAR = datetime(2026, 11, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _klien_dilarang(monkeypatch):
    """Konstruksi klien model asli apa pun menggagalkan tes (nol panggilan jaringan)."""

    def _larang(*_a: Any, **_k: Any) -> None:
        raise AssertionError("klien model tidak boleh dibuat")

    monkeypatch.setattr(modul_klien.AnthropicKlienModel, "__init__", _larang)
    monkeypatch.setattr(modul_klien.ClaudeCliKlienModel, "__init__", _larang)


@pytest.fixture
def p07(monkeypatch):
    """Daftarkan P07 dan P06 pada registri (dipulihkan otomatis)."""
    monkeypatch.setitem(FUNGSI_TERDAFTAR, "P07", FUNGSI_P07)
    monkeypatch.setitem(FUNGSI_TERDAFTAR, "P06", FUNGSI_P06)


def _atur(app, **ubah: Any) -> Settings:
    cfg = Settings(**{**_HIDUP, **ubah})
    app.dependency_overrides[get_settings] = lambda: cfg
    return cfg


def _tim(client_as):
    return client_as("tim-p07", groups=["tim-kajian"])


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
    sid = f"skl_{_hex()}"
    db.add(SekolahModel(id=sid, nama=f"SD Uji {sid}", jenjang_pendidikan_id="jp_dummy"))
    db.flush()  # FK telanjang tanpa relationship(): induk wajib di-flush lebih dulu
    pid = str(uuid.uuid4())
    db.add(
        RedesainProsesModel(
            id=pid, kode=f"P-{_hex()}", masalah_id=mid, sekolah_id=sid,
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
    return mid


def _penilaian(db: Session, masalah_id: str, status_bukti: str, prioritas: str | None) -> None:
    db.add(
        RedesainPenilaianModel(
            id=str(uuid.uuid4()), masalah_id=masalah_id, status_bukti=status_bukti,
            gap_material="Tidak", indikasi_kritis="Tidak terlihat", versi_aturan_triase="v1",
            prioritas_final=prioritas,
        )
    )  # fmt: skip
    db.flush()


def _bukti(db: Session, masalah_id: str) -> None:
    db.add(
        RedesainBuktiModel(
            id=str(uuid.uuid4()), kode=f"B-{_hex()}", masalah_id=masalah_id,
            unit_periode="SD 2026/27", jenis="Keluaran/dokumen", independen="Ya",
            klaim_didukung="Format berbeda", tanggal_versi_lokasi="Folder kurikulum",
            status_pemeriksaan="Diperiksa sesuai klaim",
        )
    )  # fmt: skip
    db.flush()


def _alternatif(db: Session, masalah_id: str, kode: str, **kw: Any) -> str:
    aid = str(uuid.uuid4())
    db.add(
        RedesainAlternatifModel(
            id=aid, kode=kode, masalah_id=masalah_id, opsi="Sederhanakan",
            alur_kini_vs_usulan="Tiga format menjadi satu", komitmen_penerima="Belum dibahas",
            **kw,
        )
    )  # fmt: skip
    db.flush()
    return aid


def _siap(db: Session, *, status_bukti: str = "Diperkuat untuk klaim", alternatif: int = 2):
    """Masalah dengan proses, penilaian, bukti sesuai, dan `alternatif` baris alternatif."""
    mid = _masalah(db)
    _penilaian(db, mid, status_bukti, "P1 - Utama")
    _bukti(db, mid)
    awalan = f"U{_hex()}"
    ids: list[str] = []
    if alternatif >= 1:
        ids.append(
            _alternatif(
                db, mid, f"{awalan}-1", status_telaah="Siap telaah", pemutus_kode_orang="O-9301",
                keputusan="Uji pada satu kelas", prasyarat_monitoring="Pantau dua minggu",
            )
        )  # fmt: skip
    if alternatif >= 2:
        ids.append(_alternatif(db, mid, f"{awalan}-2"))
    return mid, ids


def _usulan(db: Session, masalah_id: str, fungsi: str, putusan: str | None = "APPROVE") -> str:
    run_id = str(uuid.uuid4())
    db.add(
        AiRunModel(
            id=run_id, fungsi=fungsi, prompt_version="v1", prompt_hash="a" * 64,
            model_diminta="model-uji", protocol_id="uji", input_snapshot_id="b" * 64,
            sumber=[], masukan={}, keluaran={}, status_qa="LOLOS", kode_qa=[],
        )
    )  # fmt: skip
    db.flush()
    rec = AiUsulanModel(
        id=str(uuid.uuid4()), fungsi=fungsi, sasaran_jenis="REDESAIN_MASALAH",
        sasaran_id=masalah_id, job_id=str(uuid.uuid4()), ai_run_id=run_id,
        sumber_ids=[f"masalah:{masalah_id}"], diminta_oleh="tim-1", diserap_at=_DASAR,
        hasil_serap="USULAN_DIBUAT", isi={"scenario_assumptions": ["Format tunggal"]},
    )  # fmt: skip
    db.add(rec)
    db.flush()
    if putusan:
        db.add(
            AiUsulanPutusanModel(
                id=str(uuid.uuid4()), usulan_id=rec.id, putusan=putusan, actor_key="r",
                created_at=_DASAR + timedelta(minutes=1),
            )
        )  # fmt: skip
        db.flush()
    return rec.id


def _ajukan(c, masalah_id: str, usulan_p06_id: str | None = None):
    badan: dict[str, Any] = {"periode": "2026/27"}
    if usulan_p06_id is not None:
        badan["usulan_p06_id"] = usulan_p06_id
    return c.post(f"{URL}/{masalah_id}/kartu-keputusan-ai", json=badan)


def _hitung(db: Session, model: Any) -> int:
    stmt = select(func.count()).select_from(model).where(model.fungsi == "P07")
    return db.scalar(stmt) or 0


def _assert_f4_409(r, db: Session, kode: list[str]) -> None:
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "SYARAT_F4_BELUM_TERPENUHI"
    assert [d["code"] for d in body["details"]] == kode
    assert {tuple(d["loc"]) for d in body["details"]} == {("alasan",)}
    assert _hitung(db, AiUsulanModel) == 0 and _hitung(db, AiRunModel) == 0


# --- positif -------------------------------------------------------------------------------


def test_positif_202_konteks_server_dua_alternatif_dan_prioritas(app, client_as, db_session, p07):
    mid, (a1, a2) = _siap(db_session)
    _atur(app)
    c = _tim(client_as)
    r = _ajukan(c, mid)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["fungsi"] == "P07" and body["sasaran_jenis"] == "REDESAIN_MASALAH"
    assert body["sasaran_id"] == mid and "konteks_server" not in body
    rec = db_session.get(AiUsulanModel, body["id"])
    db_session.refresh(rec)
    state = rec.konteks_server["authorization_state"]
    assert state["alternatif"] == [
        {
            "alternatif_id": a1, "status_telaah": "Siap telaah", "pemutus_kode_orang": "O-9301",
            "keputusan": "Uji pada satu kelas", "prasyarat_monitoring": "Pantau dua minggu",
        },
        {
            "alternatif_id": a2, "status_telaah": "Belum ditelaah", "pemutus_kode_orang": None,
            "keputusan": None, "prasyarat_monitoring": None,
        },
    ]  # fmt: skip
    assert state["prioritas_final"] == "P1 - Utama"
    assert state["change_ditandatangani"] is False and state["sumber"] == "server"
    assert datetime.fromisoformat(state["diambil_pada"]).tzinfo is not None

    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.fungsi == "P07"
    assert run.masukan["parameter"] == {
        "masalah_id": mid,
        "periode": "2026/27",
        "versi_syarat_f4": VERSI_SYARAT_F4,
        "usulan_p06_id": None,
    }
    sumber = run.masukan["sumber"]
    assert {s["jenis"] for s in sumber} == {"REDESAIN"}
    ids = [s["source_id"] for s in sumber]
    assert ids[0] == f"masalah:{mid}" and ids[-1] == f"otorisasi:{mid}"
    assert f"alternatif:{a1}" in ids and f"alternatif:{a2}" in ids
    assert "authorization_state" not in str(run.masukan["parameter"])

    detail = c.get(f"/api/v1/ai/usulan/{body['id']}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["konteks_server"] == {"authorization_state": state}


def test_positif_dengan_usulan_p06_diterima_dirangkai_sebagai_sumber(
    app, client_as, db_session, p07
):
    mid, _ = _siap(db_session)
    uid = _usulan(db_session, mid, "P06")
    _atur(app)
    r = _ajukan(_tim(client_as), mid, uid)
    assert r.status_code == 202, r.text
    rec = db_session.get(AiUsulanModel, r.json()["id"])
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.masukan["sumber"][-1]["source_id"] == f"usulan:{uid}"
    assert run.masukan["parameter"]["usulan_p06_id"] == uid


def test_usulan_fungsi_lain_konteks_server_null(app, client_as, db_session, p07):
    mid, _ = _siap(db_session)
    _atur(app)
    r = _tim(client_as).post(f"{URL}/{mid}/opsi-ai", json={"periode": "2026/27"})
    assert r.status_code == 202, r.text
    rec = db_session.get(AiUsulanModel, r.json()["id"])
    db_session.refresh(rec)
    assert rec.fungsi == "P06" and rec.konteks_server is None
    lama = db_session.get(AiUsulanModel, _usulan(db_session, mid, "P05"))
    assert lama.konteks_server is None


def test_respons_yayasan_identik_sebelum_dan_sesudah_usulan_p07(
    app, client_as, partisipan_factory, db_session, p07
):
    mid, _ = _siap(db_session)
    _atur(app)
    partisipan_factory("tim-p07")
    c = _tim(client_as)
    sebelum = c.get(f"/api/v1/redesain/yayasan/{mid}")
    assert sebelum.status_code == 200, sebelum.text
    assert _ajukan(c, mid).status_code == 202
    sesudah = c.get(f"/api/v1/redesain/yayasan/{mid}")
    assert sesudah.status_code == 200 and sesudah.json() == sebelum.json()


# --- negatif: gerbang ----------------------------------------------------------------------


def test_tanpa_alternatif_409_alternatif_belum_ada(app, client_as, db_session, p07):
    mid, _ = _siap(db_session, alternatif=0)
    _atur(app)
    _assert_f4_409(_ajukan(_tim(client_as), mid), db_session, [KODE_ALTERNATIF_BELUM_ADA])


def test_penilaian_hipotesis_409_klaim_belum_tervalidasi(app, client_as, db_session, p07):
    mid, _ = _siap(db_session, status_bukti="Hipotesis")
    _atur(app)
    _assert_f4_409(_ajukan(_tim(client_as), mid), db_session, [KODE_KLAIM_BELUM_TERVALIDASI])


def test_periksa_syarat_p07_menambah_alternatif_di_akhir(db_session):
    mid = _masalah(db_session)
    assert periksa_syarat_p07(db_session, mid)[-1] == KODE_ALTERNATIF_BELUM_ADA
    lolos, _ = _siap(db_session)
    assert periksa_syarat_p07(db_session, lolos) == []


# --- negatif: lain -------------------------------------------------------------------------


def test_usulan_p05_sebagai_usulan_p06_422(app, client_as, db_session, p07):
    mid, _ = _siap(db_session)
    uid = _usulan(db_session, mid, "P05")
    _atur(app)
    r = _ajukan(_tim(client_as), mid, uid)
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "USULAN_BUKAN_P06"
    assert _hitung(db_session, AiUsulanModel) == 0


def test_usulan_p06_masalah_lain_422(app, client_as, db_session, p07):
    mid, _ = _siap(db_session)
    lain, _ = _siap(db_session)
    _atur(app)
    r = _ajukan(_tim(client_as), mid, _usulan(db_session, lain, "P06"))
    assert r.status_code == 422 and r.json()["error"] == "USULAN_BUKAN_P06"


def test_usulan_p06_belum_diterima_409(app, client_as, db_session, p07):
    mid, _ = _siap(db_session)
    _atur(app)
    r = _ajukan(_tim(client_as), mid, _usulan(db_session, mid, "P06", putusan=None))
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "USULAN_BELUM_DITERIMA"
    assert _hitung(db_session, AiUsulanModel) == 0


def test_fungsi_tak_terdaftar_409_fungsi_belum_aktif(app, client_as, db_session):
    mid, _ = _siap(db_session)
    _atur(app)
    r = _ajukan(_tim(client_as), mid)
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "fungsi_belum_aktif"
    assert _hitung(db_session, AiUsulanModel) == 0


def test_masalah_atau_usulan_tak_ada_404(app, client_as, db_session, p07):
    _atur(app)
    c = _tim(client_as)
    assert _ajukan(c, str(uuid.uuid4())).status_code == 404
    mid, _ = _siap(db_session)
    assert _ajukan(c, mid, str(uuid.uuid4())).status_code == 404


def test_bukan_tim_kajian_403_dan_badan_tidak_sah_422(app, client_as, db_session, p07):
    mid, _ = _siap(db_session)
    _atur(app)
    assert _ajukan(client_as("admin-1", groups=["admin"]), mid).status_code == 403
    c = _tim(client_as)
    for badan in (
        {},
        {"periode": "2026/27", "authorization_state": {}},
        {"periode": "2026/27", "usulan_p06_id": "bukan-uuid"},
    ):
        r = c.post(f"{URL}/{mid}/kartu-keputusan-ai", json=badan)
        assert r.status_code == 422, badan
