"""Tes rute `POST /api/v1/narasi/kasus/{id}/tanya-bukti-ai` (P04): usulan tanpa pengiriman.

Klien model tidak pernah dibuat; data sintetis; tanpa jaringan. Hasil hanya boleh mendarat di
`ai_usulan` (plus `ai_run` dan `async_job`): tidak di `narasi_*`, tidak ada notifikasi, dan
tidak ada permintaan bukti.
"""

from __future__ import annotations

import hashlib
import json
import logging
import smtplib
import socket
import urllib.request
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from anjab_abk_backend.ai import klien as modul_klien
from anjab_abk_backend.ai.fungsi_p04 import FUNGSI_P04, id_sumber_keputusan, id_sumber_klaim
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
from anjab_abk_backend.schemas.ai_run import StatusQaAi
from anjab_abk_backend.services.ai_run_sql import SqlAiRunService

URL = "/api/v1/narasi/kasus"
SUMBER = "/api/v1/narasi/sumber"
ANTREAN = "/api/v1/narasi/antrean"
USULAN = "/api/v1/ai/usulan"
pytestmark = pytest.mark.usefixtures("penyedia_api")

_HIDUP = {"_env_file": None, "feature_ai_narrative_draft": True}
_TEKS_SUMBER = "Kepala sekolah menetapkan jadwal rapat guru setiap hari Senin."
_KLAIM = "Guru mengikuti pelatihan penyusunan soal pada awal semester."
_KEPUTUSAN = "Menetapkan apakah pelatihan lanjutan penyusunan soal diperlukan."
_EMAIL = "kontak.fiktif@contoh.example"
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
def _tanpa_jalur_keluar(monkeypatch):
    """Klien model, SMTP, dan transport jaringan apa pun menggagalkan tes."""

    def _larang(*_a: Any, **_k: Any) -> None:
        raise AssertionError("panggilan keluar tidak boleh terjadi")

    monkeypatch.setattr(modul_klien.AnthropicKlienModel, "__init__", _larang)
    monkeypatch.setattr(modul_klien.ClaudeCliKlienModel, "__init__", _larang)
    monkeypatch.setattr(smtplib.SMTP, "__init__", _larang)
    monkeypatch.setattr(smtplib.SMTP_SSL, "__init__", _larang)
    monkeypatch.setattr(urllib.request, "urlopen", _larang)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", _larang)
    monkeypatch.setattr(socket, "create_connection", _larang)


@pytest.fixture
def p04(monkeypatch):
    """Daftarkan P04 pada registri (dipulihkan otomatis)."""
    monkeypatch.setitem(FUNGSI_TERDAFTAR, "P04", FUNGSI_P04)


@pytest.fixture
def fab(db_session: Session):
    @contextmanager
    def _fab() -> Iterator[Session]:
        yield db_session

    return _fab


def _atur(app, **ubah: Any) -> None:
    cfg = Settings(**{**_HIDUP, **ubah})
    app.dependency_overrides[get_settings] = lambda: cfg


def _tim(client_as, subject: str = "tim-tanya"):
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


def _badan(sumber_ids: list[str], **ubah: Any) -> dict[str, Any]:
    d: dict[str, Any] = {"klaim": _KLAIM, "keputusan_terkait": _KEPUTUSAN, "sumber_ids": sumber_ids}
    d.update(ubah)
    return d


def _tanya(c, narasi_id: str, badan: dict[str, Any], **kw):
    return c.post(f"{URL}/{narasi_id}/tanya-bukti-ai", json=badan, **kw)


def _hitung(db: Session) -> tuple[int, int, int]:
    return (
        db.scalar(select(func.count()).select_from(AsyncJobModel)),
        db.scalar(select(func.count()).select_from(AiRunModel)),
        db.scalar(select(func.count()).select_from(AiUsulanModel)),
    )


def _hitung_narasi(db: Session) -> list[int]:
    db.flush()
    return [db.scalar(select(func.count()).select_from(m)) for m in _TABEL_NARASI]


def _keluaran(sid: str, **isi_ubah: Any) -> dict[str, Any]:
    isi: dict[str, Any] = {
        "material": True,
        "materiality_rationale": "pelatihan tidak tercatat pada materi",
        "one_neutral_question": "Bagaimana pelatihan itu dicatat oleh sekolah?",
        "why_ask": "agar Tim memahami dasar klaim",
        "preferred_role": "Wakil kepala sekolah bidang kurikulum",
        "alternatives": [],
        "limitations": ["hanya memeriksa materi yang diberikan"],
    }
    isi.update(isi_ubah)
    return {
        "status": "AI_DRAFT",
        "source_refs": [{"source_id": sid, "source_hash": "h"}],
        "cited_spans": [{"source_id": sid, "span": "jadwal rapat guru"}],
        "confidence_reason": "kutipan langsung",
        "unknowns": [],
        "contradictions": [],
        "human_review_required": True,
        "isi": isi,
    }


def _tutup(db: Session, run_id: str, status: StatusQaAi, kode, keluaran) -> None:
    SqlAiRunService(db, Settings(**_HIDUP)).tutup(
        run_id, status, kode, keluaran, None, None, None, None
    )


def _siap(c, **kw) -> tuple[dict, str]:
    """Kasus + satu sumber berizin."""
    return _kasus(c), _sumber(c, **kw)


def test_positif_202_kunci_kontrak_dan_klaim_serta_keputusan_hanya_lewat_sumber(
    app, client_as, db_session, p04
):
    c = _tim(client_as, "tim-positif")
    _atur(app)
    k, sid = _siap(c)
    r = _tanya(c, k["id"], _badan([sid]))
    assert r.status_code == 202, r.text
    body = r.json()
    assert set(body) == KUNCI_202
    for dilarang in ("ai_run_id", "sumber_ids", "diminta_oleh", "actor_key", "isi", "amplop"):
        assert dilarang not in body
    assert body["fungsi"] == "P04" and body["sasaran_jenis"] == "NARASI_KASUS"
    assert body["sasaran_id"] == k["id"] and body["diserap_at"] is None
    assert body["putusan_terakhir"] is None
    assert _KLAIM not in r.text and _KEPUTUSAN not in r.text  # tidak digaungkan di 202
    rec = db_session.get(AiUsulanModel, body["id"])
    run = db_session.get(AiRunModel, rec.ai_run_id)
    assert run.fungsi == "P04" and run.status_qa == "MENUNGGU"
    # parameter hanya dua kode berpola; teks bebas tidak ada di sana.
    assert run.masukan["parameter"] == {"narasi_id": k["id"], "periode": "2026-27"}
    assert _KLAIM not in json.dumps(run.masukan["parameter"])
    sk, sd = id_sumber_klaim(_KLAIM), id_sumber_keputusan(_KEPUTUSAN)
    daftar = run.masukan["sumber"]
    assert [x["source_id"] for x in daftar] == [sid, sk, sd]
    assert daftar[1]["teks"] == _KLAIM and daftar[1]["jenis"] == "SINTETIS"
    assert daftar[1]["source_hash"] == hashlib.sha256(_KLAIM.encode()).hexdigest()
    assert daftar[2]["teks"] == _KEPUTUSAN and daftar[2]["jenis"] == "SINTETIS"
    # `sumber_ids` mencatat penanda itu apa adanya; bukan baris `narasi_sumber`.
    assert rec.sumber_ids == [sid, sk, sd] and rec.diminta_oleh == "tim-positif"
    assert sk.startswith("klaim:") and sd.startswith("keputusan:")
    assert db_session.scalar(select(func.count()).select_from(NarasiAiPermintaanModel)) == 0


def test_serap_material_true_dan_material_false_pertanyaan_null_usulan_dibuat(
    app, client_as, db_session, p04
):
    c = _tim(client_as)
    _atur(app)
    k, sid = _siap(c)
    for ubah in (
        {},
        {"material": False, "one_neutral_question": None, "why_ask": None, "preferred_role": None},
    ):
        r = _tanya(c, k["id"], _badan([sid]))
        assert r.status_code == 202, r.text
        uid = r.json()["id"]
        run_id = db_session.get(AiUsulanModel, uid).ai_run_id
        _tutup(db_session, run_id, StatusQaAi.LOLOS, [], _keluaran(sid, **ubah))
        assert serap_usulan(db_session, uid) is not None
        db_session.flush()
        d = c.get(f"{USULAN}/{uid}").json()
        assert d["hasil_serap"] == "USULAN_DIBUAT", d
        assert d["isi"]["material"] is ubah.get("material", True)
        assert d["isi"]["one_neutral_question"] == ubah.get(
            "one_neutral_question", "Bagaimana pelatihan itu dicatat oleh sekolah?"
        )
        # Usulan tidak terkirim: tidak ada kunci pengiriman pada respons mana pun.
        assert not {"dikirim", "terkirim", "kirim"} & set(d)


@pytest.mark.parametrize(
    ("ubah", "kode"),
    [
        ({"material": True, "one_neutral_question": None}, ["ATURAN_P04_DILANGGAR"]),
        ({"material": True, "one_neutral_question": "   "}, ["ATURAN_P04_DILANGGAR"]),
        ({"material": False}, ["ATURAN_P04_DILANGGAR"]),
        ({"one_neutral_question": "Siapa yang mencatat? Kapan?"}, ["LEBIH_DARI_SATU_PERTANYAAN"]),
        (
            {"material": False, "one_neutral_question": "Siapa? Kapan?"},
            ["ATURAN_P04_DILANGGAR", "LEBIH_DARI_SATU_PERTANYAAN"],
        ),
    ],
)
def test_keluaran_melanggar_aturan_berakhir_manual_dengan_kode_benar_setelah_diserap(
    app, client_as, db_session, p04, ubah, kode
):
    c = _tim(client_as)
    _atur(app)
    k, sid = _siap(c)
    uid = _tanya(c, k["id"], _badan([sid])).json()["id"]
    run_id = db_session.get(AiUsulanModel, uid).ai_run_id
    _tutup(db_session, run_id, StatusQaAi.LOLOS, [], _keluaran(sid, **ubah))
    assert serap_usulan(db_session, uid) is not None
    db_session.flush()
    db_session.expire_all()
    rec = db_session.get(AiUsulanModel, uid)
    assert rec.hasil_serap == "MANUAL" and list(rec.kode_serap) == kode
    assert rec.isi is None and rec.amplop is None and rec.output_hash is None


def test_material_true_tanpa_tanda_tanya_lolos_apa_adanya(app, client_as, db_session, p04):
    """Perilaku yang dilaporkan: tidak ada aturan baru untuk pertanyaan tanpa tanda tanya."""
    c = _tim(client_as)
    _atur(app)
    k, sid = _siap(c)
    uid = _tanya(c, k["id"], _badan([sid])).json()["id"]
    run_id = db_session.get(AiUsulanModel, uid).ai_run_id
    ubah = {"one_neutral_question": "Jelaskan bagaimana pelatihan itu dicatat"}
    _tutup(db_session, run_id, StatusQaAi.LOLOS, [], _keluaran(sid, **ubah))
    assert serap_usulan(db_session, uid) is not None
    db_session.flush()
    assert c.get(f"{USULAN}/{uid}").json()["hasil_serap"] == "USULAN_DIBUAT"


def test_tidak_ada_tulisan_narasi_dan_tidak_ada_jalur_keluar(
    app, client_as, db_session, p04, fab, monkeypatch
):
    c = _tim(client_as)
    _atur(app)
    k, sid = _siap(c)
    status_awal = db_session.get(NarasiKasusModel, k["id"]).status
    antrean_awal = c.get(ANTREAN).json()
    narasi_awal = _hitung_narasi(db_session)
    riwayat_awal = c.get(f"{URL}/{k['id']}/riwayat").json()
    ditulis: set[str] = set()

    def _catat(session: Session, _ctx: Any, _inst: Any) -> None:
        ditulis.update(type(o).__name__ for o in (*session.new, *session.dirty, *session.deleted))

    event.listen(db_session, "before_flush", _catat)
    try:
        r = _tanya(c, k["id"], _badan([sid]))
        assert r.status_code == 202, r.text
        uid = r.json()["id"]
        run_id = db_session.get(AiUsulanModel, uid).ai_run_id
        _tutup(db_session, run_id, StatusQaAi.LOLOS, [], _keluaran(sid))
        assert serap_usulan(db_session, uid) is not None
        penyerap.serap_tertunda(fab)  # penyerap narasi tidak boleh menyentuh run P04
        db_session.flush()
    finally:
        event.remove(db_session, "before_flush", _catat)
    assert ditulis <= {"AiUsulanModel", "AiRunModel", "AsyncJobModel"}, ditulis
    assert ditulis  # penjaga: pendengar memang menangkap sesuatu
    assert _hitung_narasi(db_session) == narasi_awal
    db_session.expire_all()
    assert db_session.get(NarasiKasusModel, k["id"]).status == status_awal
    assert c.get(ANTREAN).json() == antrean_awal
    assert c.get(f"{URL}/{k['id']}/riwayat").json() == riwayat_awal
    daftar = c.get(USULAN, params={"fungsi": "P04"}).json()["items"][0]
    for dilarang in ("sumber_ids", "ai_run_id", "diminta_oleh"):
        assert dilarang not in daftar
    assert "actor_key" not in json.dumps(daftar)


def test_flag_mati_409_tanpa_baris_tanpa_baca_dan_tanpa_klien(app, client_as, db_session, p04):
    c = _tim(client_as)
    _atur(app, feature_ai_narrative_draft=False)
    awal = _hitung(db_session)
    # Kasus dan sumber tak ada: 409 (bukan 404/422) membuktikan flag diperiksa sebelum membaca.
    r = _tanya(c, str(uuid.uuid4()), _badan([str(uuid.uuid4())]))
    assert r.status_code == 409 and r.json()["error"] == "feature_disabled", r.text
    assert _hitung(db_session) == awal


def test_p04_tak_terdaftar_409_fungsi_belum_aktif_tanpa_baris(app, client_as, db_session):
    c = _tim(client_as)
    _atur(app)
    k, sid = _siap(c)
    awal = _hitung(db_session)
    assert "P04" not in FUNGSI_TERDAFTAR
    r = _tanya(c, k["id"], _badan([sid]))
    assert r.status_code == 409 and r.json()["error"] == "fungsi_belum_aktif", r.text
    assert _hitung(db_session) == awal


def test_kasus_tak_ada_404(app, client_as, db_session, p04):
    c = _tim(client_as)
    _atur(app)
    sid = _sumber(c)
    awal = _hitung(db_session)
    assert _tanya(c, str(uuid.uuid4()), _badan([sid])).status_code == 404
    assert _hitung(db_session) == awal


def test_badan_tidak_sah_422_tanpa_baris(app, client_as, db_session, p04):
    c = _tim(client_as)
    _atur(app)
    k, sid = _siap(c)
    awal = _hitung(db_session)
    buruk = [
        _badan([sid], klaim="abcd"),  # 4 karakter
        _badan([sid], klaim="  abcd  "),  # 4 setelah dipangkas
        _badan([sid], klaim=" " * 10),
        _badan([sid], klaim="x" * 2001),
        _badan([sid], keputusan_terkait="abcd"),
        _badan([sid], keputusan_terkait="x" * 501),
        _badan([]),  # sumber_ids kosong
        {"klaim": _KLAIM, "keputusan_terkait": _KEPUTUSAN},  # sumber_ids hilang
        {"keputusan_terkait": _KEPUTUSAN, "sumber_ids": [sid]},  # klaim hilang
        _badan([sid], lain="x"),
        _badan([sid] * 51),  # lebih dari 50 id
    ]
    for badan in buruk:
        r = _tanya(c, k["id"], badan)
        assert r.status_code == 422, (badan.get("klaim", "")[:12], r.text)
    # Batas pas diterima: 5 dan 2.000 karakter, 5 dan 500 karakter.
    ok = _tanya(c, k["id"], _badan([sid], klaim="x" * 2000, keputusan_terkait="y" * 500))
    assert ok.status_code == 202, ok.text
    assert _hitung(db_session)[2] == awal[2] + 1


def test_sumber_tak_dikenal_422_dan_izin_palsu_409(app, client_as, db_session, p04):
    c = _tim(client_as)
    _atur(app)
    k, sid = _siap(c)
    tanpa_izin = _sumber(c, izin_ai=False)
    awal = _hitung(db_session)
    r = _tanya(c, k["id"], _badan([sid, str(uuid.uuid4())]))
    assert r.status_code == 422, r.text
    r = _tanya(c, k["id"], _badan([sid, tanpa_izin]))
    assert r.status_code == 409 and r.json()["error"] == "izin_sumber_tidak_ada", r.text
    assert _hitung(db_session) == awal


@pytest.mark.parametrize("medan", ["klaim", "keputusan_terkait"])
def test_email_sintetis_pada_tiap_field_diblokir_nol_klien_dan_tidak_bocor(
    app, client_as, db_session, p04, caplog, medan
):
    c = _tim(client_as)
    _atur(app)
    k, sid = _siap(c)
    badan = _badan([sid], **{medan: f"Isian uji yang memuat {_EMAIL} di dalamnya."})
    with caplog.at_level(logging.DEBUG):
        r = _tanya(c, k["id"], badan)
        assert r.status_code == 202, r.text
        uid = r.json()["id"]
        rec = db_session.get(AiUsulanModel, uid)
        run = db_session.get(AiRunModel, rec.ai_run_id)
        assert run.status_qa == "DIBLOKIR" and list(run.kode_qa) == ["PII_DITEMUKAN"]
        assert run.masukan is None  # nol masukan tersimpan; klien tak pernah dibuat (fixture)
        assert db_session.get(AsyncJobModel, rec.job_id).status == "MANUAL_REVIEW"
        assert serap_usulan(db_session, uid) is not None
        db_session.flush()
    db_session.expire_all()
    rec = db_session.get(AiUsulanModel, uid)
    assert rec.hasil_serap == "MANUAL" and list(rec.kode_serap) == ["PII_DITEMUKAN"]
    assert rec.isi is None and rec.amplop is None
    for tempat in (r.text, caplog.text, json.dumps(run.kode_qa), json.dumps(rec.kode_serap)):
        assert _EMAIL not in tempat
    # Penanda sumber (bukan teksnya) boleh tercatat; teks klaim/keputusan tidak ada di sana.
    assert "kontak.fiktif" not in json.dumps(rec.sumber_ids)


def test_sumber_jenis_campuran_ditolak_dan_jenis_klaim_mengikuti_sumber_pertama(
    app, client_as, db_session, p04
):
    c = _tim(client_as)
    _atur(app)
    k = _kasus(c)
    ok = _sumber(c)
    ditolak = _sumber(c, jenis="DOKUMEN_RESMI")
    r = _tanya(c, k["id"], _badan([ok, ditolak]))
    assert r.status_code == 202, r.text
    run = db_session.get(AiRunModel, db_session.get(AiUsulanModel, r.json()["id"]).ai_run_id)
    assert run.status_qa == "DIBLOKIR" and list(run.kode_qa) == ["JENIS_DITOLAK"]
    assert run.masukan is None
    # Urutan terbalik pada kasus lain: jenis klaim dan keputusan ikut sumber PERTAMA
    # (DOKUMEN_RESMI), dan seluruh pengajuan tetap diblokir gerbang.
    k2 = _kasus(c)
    r2 = _tanya(c, k2["id"], _badan([ditolak, ok]))
    assert r2.status_code == 202, r2.text
    run2 = db_session.get(AiRunModel, db_session.get(AiUsulanModel, r2.json()["id"]).ai_run_id)
    assert run2.status_qa == "DIBLOKIR" and list(run2.kode_qa) == ["JENIS_DITOLAK"]


def test_pengajuan_ulang_klaim_sama_menghasilkan_source_id_dan_snapshot_sama(
    app, client_as, db_session, p04
):
    c = _tim(client_as)
    _atur(app)
    k, sid = _siap(c)
    snapshot, ids = [], []
    for _ in range(2):
        r = _tanya(c, k["id"], _badan([sid]))
        assert r.status_code == 202, r.text
        uid = r.json()["id"]
        rec = db_session.get(AiUsulanModel, uid)
        run = db_session.get(AiRunModel, rec.ai_run_id)
        snapshot.append(run.input_snapshot_id)
        ids.append(list(rec.sumber_ids))
        _tutup(db_session, run.id, StatusQaAi.KARANTINA, ["TANPA_SITASI"], None)
        serap_usulan(db_session, uid)
    assert snapshot[0] == snapshot[1] and ids[0] == ids[1]
    # Klaim berbeda -> source_id dan snapshot berbeda.
    r = _tanya(c, k["id"], _badan([sid], klaim=_KLAIM + " Tambahan."))
    rec = db_session.get(AiUsulanModel, r.json()["id"])
    assert list(rec.sumber_ids) != ids[0]
    assert db_session.get(AiRunModel, rec.ai_run_id).input_snapshot_id != snapshot[0]


def test_kasus_periode_di_luar_pola_menjadi_kode_sah_bukan_500_atau_422(
    app, client_as, db_session, p04
):
    c = _tim(client_as)
    _atur(app)
    sid = _sumber(c)
    for periode, kode in (("2026/27", "2026-27"), ("2026/27 ganjil", "2026-27-ganjil"), (" ", "-")):
        k = _kasus(c, periode=periode)
        r = _tanya(c, k["id"], _badan([sid]))
        assert r.status_code == 202, (periode, r.text)
        run = db_session.get(AiRunModel, db_session.get(AiUsulanModel, r.json()["id"]).ai_run_id)
        assert run.masukan["parameter"] == {"narasi_id": k["id"], "periode": kode}


def test_idempotency_retry_membalas_tersimpan_dan_pemeriksaan_di_dalam_aksi(
    app, client_as, db_session, p04
):
    c = _tim(client_as)
    _atur(app)
    k, sid = _siap(c)
    h = {"Idempotency-Key": "kunci-tanya-1"}
    r1 = _tanya(c, k["id"], _badan([sid]), headers=h)
    assert r1.status_code == 202, r1.text
    awal = _hitung(db_session)
    # Tanpa key, permintaan sama kini 409 `usulan_berjalan` (usulan belum diserap).
    r_tanpa = _tanya(c, k["id"], _badan([sid]))
    assert r_tanpa.status_code == 409 and r_tanpa.json()["error"] == "usulan_berjalan"
    # Key sama: respons tersimpan (200), tanpa baris baru, walau usulan masih berjalan.
    r2 = _tanya(c, k["id"], _badan([sid]), headers=h)
    assert r2.status_code == 200 and r2.json() == r1.json()
    assert _hitung(db_session) == awal
    # Sesudah diserap dan flag dimatikan, key sama tetap membalas tersimpan (bukan 409 flag).
    uid = r1.json()["id"]
    _tutup(
        db_session,
        db_session.get(AiUsulanModel, uid).ai_run_id,
        StatusQaAi.KARANTINA,
        ["TANPA_SITASI"],
        None,
    )
    serap_usulan(db_session, uid)
    _atur(app, feature_ai_narrative_draft=False)
    r3 = _tanya(c, k["id"], _badan([sid]), headers=h)
    assert r3.status_code == 200 and r3.json() == r1.json()
    # Key baru dengan flag mati: 409 `feature_disabled`, bukan balasan lama.
    r4 = _tanya(c, k["id"], _badan([sid]), headers={"Idempotency-Key": "kunci-tanya-2"})
    assert r4.status_code == 409 and r4.json()["error"] == "feature_disabled"
    assert _hitung(db_session) == awal


def test_penolakan_404_tidak_disimpan_sebagai_balasan_idempoten(app, client_as, db_session, p04):
    c = _tim(client_as)
    _atur(app)
    sid = _sumber(c)
    h = {"Idempotency-Key": "kunci-tanya-404"}
    kid = str(uuid.uuid4())
    assert _tanya(c, kid, _badan([sid]), headers=h).status_code == 404
    assert _tanya(c, kid, _badan([sid]), headers=h).status_code == 404


def test_otorisasi_401_403_mendahului_422_dan_404(app, anon_client, client_as, p04):
    _atur(app)
    kid = str(uuid.uuid4())
    path = f"{URL}/{kid}/tanya-bukti-ai"
    valid = _badan([str(uuid.uuid4())])
    assert anon_client.post(path, json=valid).status_code == 401
    assert anon_client.post(path, json={}).status_code == 401
    for grup in ("admin", "sekolah-pengisi"):
        c = client_as("x-" + grup, groups=[grup])
        assert c.post(path, json=valid).status_code == 403, grup  # kasus tak ada: bukan 404
        assert c.post(path, json={}).status_code == 403, grup  # badan salah: bukan 422
    tim = _tim(client_as)
    assert tim.post(path, json={}).status_code == 422
    assert tim.post(path, json=_badan([])).status_code == 422
    assert tim.post(path, json=valid).status_code == 404  # kasus tak ada; sumber belum dibaca


def test_openapi_memuat_rute_dan_registri_produksi_tanpa_p04(app, anon_client):
    paths = anon_client.get("/openapi.json").json()["paths"]
    rute = paths["/api/v1/narasi/kasus/{narasi_id}/tanya-bukti-ai"]["post"]
    assert "202" in rute["responses"]
    assert rute["operationId"] == "narasi_kasus_tanya_bukti_ai_ajukan"
    assert "P04" not in FUNGSI_TERDAFTAR
