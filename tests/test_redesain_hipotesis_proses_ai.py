"""Tes rute `POST /api/v1/redesain/masalah/{id}/hipotesis-proses-ai` (P05).

Klien model sungguhan tidak pernah dibuat; data sintetis; tanpa jaringan. Semua sumber yang
terkirim berjenis `REDESAIN`; hasil hanya `ai_usulan` bersasaran `REDESAIN_MASALAH`.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from anjab_abk_backend.ai import klien as modul_klien
from anjab_abk_backend.ai.fungsi_p05 import FUNGSI_P05
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.sumber_redesain import AWALAN_SUMBER_REDESAIN, rakit_sumber_redesain
from anjab_abk_backend.config import Settings, get_settings
from anjab_abk_backend.models import (
    AiRunModel,
    AiUsulanModel,
    RedesainBuktiModel,
    RedesainKonfirmasiModel,
    RedesainKonteksModel,
    RedesainKoreksiLangkahModel,
    RedesainLangkahModel,
    RedesainMasalahModel,
    RedesainMasalahUraianTugasModel,
    RedesainProsesModel,
    SekolahModel,
    TiUraianTugasModel,
)

URL = "/api/v1/redesain/masalah"
pytestmark = pytest.mark.usefixtures("penyedia_api")

_HIDUP = {
    "_env_file": None,
    "feature_ai_narrative_draft": True,
    "ai_jenis_sumber_diizinkan": ["REDESAIN"],
}
_CERITA = "Cerita bebas sebelum dugaan ditampilkan xq7"
_DRAF = "Konfirmasi draf yang belum dikirim zr4"


@pytest.fixture(autouse=True)
def _klien_dilarang(monkeypatch):
    """Konstruksi klien model asli apa pun menggagalkan tes (nol panggilan jaringan)."""

    def _larang(*_a: Any, **_k: Any) -> None:
        raise AssertionError("klien model tidak boleh dibuat")

    monkeypatch.setattr(modul_klien.AnthropicKlienModel, "__init__", _larang)
    monkeypatch.setattr(modul_klien.ClaudeCliKlienModel, "__init__", _larang)


@pytest.fixture
def p05(monkeypatch):
    """Daftarkan P05 pada registri (dipulihkan otomatis)."""
    monkeypatch.setitem(FUNGSI_TERDAFTAR, "P05", FUNGSI_P05)


def _atur(app, **ubah: Any) -> Settings:
    cfg = Settings(**{**_HIDUP, **ubah})
    app.dependency_overrides[get_settings] = lambda: cfg
    return cfg


def _tim(client_as):
    return client_as("tim-p05", groups=["tim-kajian"])


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


def _proses(db: Session, masalah_id: str, n_langkah: int) -> tuple[str, list[str]]:
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
    lids = []
    for i in range(n_langkah):
        lid = str(uuid.uuid4())
        db.add(
            RedesainLangkahModel(
                id=lid, proses_id=pid, kode=f"L-{_hex()}", urutan=i + 1, tahap=f"Tahap {i}",
                pemicu_input="Akhir semester", pelaksana="Guru", pekerjaan_sistem="Mengisi",
                keluaran_penerima="Lembar nilai", status_langkah="Dicatat",
            )
        )  # fmt: skip
        lids.append(lid)
    db.flush()
    return pid, lids


def _bukti(db: Session, masalah_id: str, n: int, langkah_id: str | None = None) -> None:
    for _ in range(n):
        db.add(
            RedesainBuktiModel(
                id=str(uuid.uuid4()), kode=f"B-{_hex()}", masalah_id=masalah_id,
                langkah_id=langkah_id, unit_periode="SD 2026/27", jenis="Dokumen",
                independen="Tidak", klaim_didukung="Format berbeda",
                tanggal_versi_lokasi="Folder kurikulum", catatan_privasi_gap="privasi-gap-w9",
            )
        )  # fmt: skip
    db.flush()


def _konfirmasi(db: Session, masalah_id: str, *, terkirim: bool, cerita: str) -> str:
    kid = str(uuid.uuid4())
    db.add(
        RedesainKonfirmasiModel(
            id=kid, masalah_id=masalah_id, kode_orang=f"O-{_hex()[:4]}", sekolah_id="skl-x",
            tanggal=date(2026, 10, 1), cerita_sebelum=cerita,
            koreksi="Penumpukan di tanda tangan" if terkirim else _DRAF,
            dikirim_pada=datetime(2026, 10, 2, tzinfo=UTC) if terkirim else None,
            status="terkirim" if terkirim else "draf",
        )
    )  # fmt: skip
    db.flush()
    return kid


def _ajukan(c, masalah_id: str, periode: str = "2026/27"):
    return c.post(f"{URL}/{masalah_id}/hipotesis-proses-ai", json={"periode": periode})


def _hitung_p05(db: Session) -> int:
    stmt = select(func.count()).select_from(AiUsulanModel).where(AiUsulanModel.fungsi == "P05")
    return db.scalar(stmt) or 0


def _run(db: Session, usulan_id: str) -> AiRunModel:
    rec = db.get(AiUsulanModel, usulan_id)
    db.refresh(rec)
    return db.get(AiRunModel, rec.ai_run_id)


# --- positif -------------------------------------------------------------------------------


def test_positif_202_sumber_redesain_dengan_awalan_benar(app, client_as, db_session, p05):
    mid = _masalah(db_session)
    pid, (l1, l2) = _proses(db_session, mid, 2)
    _bukti(db_session, mid, 1, langkah_id=l1)
    _atur(app)
    r = _ajukan(_tim(client_as), mid)
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["fungsi"] == "P05" and body["sasaran_jenis"] == "REDESAIN_MASALAH"
    assert body["sasaran_id"] == mid
    run = _run(db_session, body["id"])
    assert run.fungsi == "P05" and run.status_qa == "MENUNGGU"
    assert run.masukan["parameter"] == {"masalah_id": mid, "periode": "2026/27"}
    sumber = run.masukan["sumber"]
    assert {s["jenis"] for s in sumber} == {"REDESAIN"}
    ids = [s["source_id"] for s in sumber]
    assert ids[:4] == [f"masalah:{mid}", f"proses:{pid}", f"langkah:{l1}", f"langkah:{l2}"]
    assert ids[4].startswith("bukti:") and len(ids) == 5
    for s in sumber:
        assert s["source_id"].startswith(AWALAN_SUMBER_REDESAIN)
        assert s["source_hash"] == hashlib.sha256(s["teks"].encode()).hexdigest()
    assert "privasi-gap-w9" not in "".join(s["teks"] for s in sumber)
    assert "status_pemeriksaan: Belum diperiksa" in sumber[4]["teks"]


def test_task_links_masuk_teks_sumber_masalah(db_session):
    mid = _masalah(db_session)
    _proses(db_session, mid, 1)
    ut = TiUraianTugasModel(id=f"ut_{_hex()}", uraian="Menyusun rekap nilai semester")
    db_session.add(ut)
    db_session.flush()
    db_session.add(RedesainMasalahUraianTugasModel(masalah_id=mid, uraian_tugas_id=ut.id))
    db_session.flush()
    sumber = rakit_sumber_redesain(db_session, mid, sertakan_konfirmasi=False)
    assert sumber[0].source_id == f"masalah:{mid}"
    assert f"task_links: {ut.id} (Menyusun rekap nilai semester)" in sumber[0].teks


def test_konfirmasi_hanya_terkirim_dan_tanpa_cerita_sebelum(app, client_as, db_session, p05):
    mid = _masalah(db_session)
    _pid, (l1,) = _proses(db_session, mid, 1)
    kirim = _konfirmasi(db_session, mid, terkirim=True, cerita=_CERITA)
    draf = _konfirmasi(db_session, mid, terkirim=False, cerita=_CERITA)
    tim_id, kirim_k, draf_k = (str(uuid.uuid4()) for _ in range(3))
    db_session.add_all(
        [
            RedesainKoreksiLangkahModel(id=tim_id, langkah_id=l1, kode_orang="O-0001", isi="a"),
            RedesainKoreksiLangkahModel(
                id=kirim_k, langkah_id=l1, konfirmasi_id=kirim, kode_orang="O-0002", isi="b"
            ),
            RedesainKoreksiLangkahModel(
                id=draf_k, langkah_id=l1, konfirmasi_id=draf, kode_orang="O-0003", isi="c"
            ),
        ]
    )
    db_session.flush()
    _atur(app)
    r = _ajukan(_tim(client_as), mid)
    assert r.status_code == 202, r.text
    sumber = _run(db_session, r.json()["id"]).masukan["sumber"]
    ids = {s["source_id"] for s in sumber}
    assert f"konfirmasi:{kirim}" in ids and f"konfirmasi:{draf}" not in ids
    assert {f"koreksi:{tim_id}", f"koreksi:{kirim_k}"} <= ids
    assert f"koreksi:{draf_k}" not in ids
    semua = "\n".join(s["teks"] for s in sumber)
    assert _CERITA not in semua and "cerita_sebelum" not in semua and _DRAF not in semua
    tanpa = rakit_sumber_redesain(db_session, mid, sertakan_konfirmasi=False)
    ids_tanpa = {s.source_id for s in tanpa}
    assert not any(i.startswith("konfirmasi:") for i in ids_tanpa)
    assert f"koreksi:{tim_id}" in ids_tanpa and f"koreksi:{kirim_k}" not in ids_tanpa


# --- negatif -------------------------------------------------------------------------------


def test_settings_bawaan_409_tanpa_usulan_baru(app, client_as, db_session):
    mid = _masalah(db_session)
    _proses(db_session, mid, 1)
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)
    r = _ajukan(_tim(client_as), mid)
    assert r.status_code == 409, r.text
    assert _hitung_p05(db_session) == 0


def test_fungsi_tak_terdaftar_409_fungsi_belum_aktif(app, client_as, db_session):
    mid = _masalah(db_session)
    _proses(db_session, mid, 1)
    _atur(app)
    r = _ajukan(_tim(client_as), mid)
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "fungsi_belum_aktif"
    assert _hitung_p05(db_session) == 0


def test_masalah_tak_ada_404(app, client_as, db_session, p05):
    _atur(app)
    assert _ajukan(_tim(client_as), str(uuid.uuid4())).status_code == 404


@pytest.mark.parametrize("n_langkah", [None, 0])
def test_tanpa_proses_atau_proses_tanpa_langkah_409(app, client_as, db_session, p05, n_langkah):
    mid = _masalah(db_session)
    if n_langkah is not None:
        _proses(db_session, mid, n_langkah)
    _atur(app)
    r = _ajukan(_tim(client_as), mid)
    assert r.status_code == 409, r.text
    assert r.json()["error"] == "SUMBER_PROSES_BELUM_TERHUBUNG"
    assert _hitung_p05(db_session) == 0


def test_sumber_61_422_sumber_terlalu_banyak_dan_60_lolos(app, client_as, db_session, p05):
    mid = _masalah(db_session)
    _proses(db_session, mid, 1)
    _bukti(db_session, mid, 57)  # 1 masalah + 1 proses + 1 langkah + 57 bukti = 60
    _atur(app)
    c = _tim(client_as)
    lain = _masalah(db_session)
    _proses(db_session, lain, 1)
    _bukti(db_session, lain, 58)  # 61
    r = _ajukan(c, lain)
    assert r.status_code == 422, r.text
    assert r.json()["error"] == "SUMBER_TERLALU_BANYAK"
    assert _ajukan(c, mid).status_code == 202


def test_bukan_tim_kajian_403(app, client_as, db_session, p05):
    mid = _masalah(db_session)
    _proses(db_session, mid, 1)
    _atur(app)
    assert _ajukan(client_as("admin-1", groups=["admin"]), mid).status_code == 403


def test_badan_tidak_sah_422(app, client_as, db_session, p05):
    mid = _masalah(db_session)
    _atur(app)
    c = _tim(client_as)
    for badan in ({}, {"periode": "2026/27 ganjil"}, {"periode": "2026/27", "catatan": "x"}):
        r = c.post(f"{URL}/{mid}/hipotesis-proses-ai", json=badan)
        assert r.status_code == 422, badan
