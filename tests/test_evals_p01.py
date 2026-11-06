"""Uji harness evaluasi P01 (``evals/p01/kasus.json``) dengan klien tiruan: tanpa jaringan.

Yang dibuktikan: ``kasus.json`` lolos format harness, penilai MEMBACA ``harapan`` bentuk P01
(sifat fakta, span fakta, angka baru, pola terlarang, fakta pada gap), dan keluaran tiruan yang
melanggar benar-benar gagal (exit 1). Perilaku MODEL sungguhan tidak terbukti di sini.
"""

from __future__ import annotations

import copy
import io
import json
from pathlib import Path
from typing import Any

import pytest

from anjab_abk_backend.ai.klien import JawabanModel
from anjab_abk_backend.config import Settings
from evals import jalankan
from evals.kasus import DEFINISI_FUNGSI, Kasus, KasusRusak, muat_kasus
from evals.penilai import nilai

_DEF = DEFINISI_FUNGSI["P01"]
_BERKAS = _DEF.berkas
_KUNCI_UJI = "kunci-uji-tiruan-p01z4"


def _kasus_semua() -> list[Kasus]:
    return muat_kasus(_BERKAS, "P01", _DEF)


def _kasus(id_: str) -> Kasus:
    return next(k for k in _kasus_semua() if k.id == id_)


def _span(k: Kasus) -> str:
    return " ".join(k.sumber[0].teks.split()[:4])


def _isi_ideal(k: Kasus) -> dict[str, Any]:
    """Isi yang memenuhi ``harapan`` kasus ``k``: fakta = awal teks sumber, sifat sah."""
    gap = k.harapan.status_qa == ["EVIDENCE_GAP"]
    sifat = (k.harapan.hanya_sifat or ["DESKRIPTIF_DOKUMEN"])[0]
    fakta = []
    if not gap:
        fakta = [
            {"fakta": _span(k), "sifat": sifat, "source_id": "s1", "span": _span(k)}
        ]  # fmt: skip
    return {
        "factual_extracts": fakta,
        "source_quality": [{"source_id": "s1", "penilaian": "CUKUP", "alasan": "teks utuh"}],
        "uncertainties": [],
        "limitations": ["tidak memeriksa makna parafrasa"],
    }


def _amplop(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
    gap = k.harapan.status_qa == ["EVIDENCE_GAP"]
    return {
        "status": "EVIDENCE_GAP" if gap else "AI_DRAFT",
        "source_refs": [],
        "cited_spans": [] if gap else [{"source_id": "s1", "span": _span(k)}],
        "confidence_reason": "kutipan",
        "unknowns": ["sumber tidak memuat prosedur"] if gap else [],
        "contradictions": [],
        "human_review_required": True,
        "isi": isi,
    }


def _jawab(teks: str) -> JawabanModel:
    return JawabanModel(
        teks=teks, model_dilayani="model-tiruan", stop_reason="end_turn",
        input_tokens=5, output_tokens=5,
    )  # fmt: skip


class KlienOrakel:
    """Klien tiruan: menjawab tiap kasus dari teks sumber pada masukan."""

    def __init__(self, ubah=None) -> None:
        self.ubah = ubah or (lambda _k, isi: isi)
        self.panggilan = 0
        self.per_teks = {k.sumber[0].teks: k for k in _kasus_semua()}

    def panggil(self, instruksi: str, masukan_json: str, skema: dict[str, Any]) -> JawabanModel:
        self.panggilan += 1
        k = self.per_teks[json.loads(masukan_json)["sumber"][0]["teks"]]
        isi = self.ubah(k, _isi_ideal(k))
        return _jawab(json.dumps(_amplop(k, isi)))


def _jalan(monkeypatch, klien, argv_extra=None) -> tuple[int, list[dict[str, Any]], str]:
    monkeypatch.setattr(jalankan, "_tidur", lambda _d: None)
    monkeypatch.setattr(jalankan, "AnthropicKlienModel", lambda _s, **_kw: klien)
    out, err = io.StringIO(), io.StringIO()
    argv = ["--fungsi", "P01", "--penyedia", "API_ANTHROPIC", *(argv_extra or [])]
    kode = jalankan.main(argv, {"ANTHROPIC_API_KEY": _KUNCI_UJI, "EVAL_ULANG": "1"}, out, err)
    baris = out.getvalue().splitlines()
    assert baris[-1].startswith("#EVAL ")
    return kode, [json.loads(b) for b in baris[:-1]], baris[-1]


# --- berkas kasus ---


def test_kasus_p01_lolos_format_harness_jumlah_dan_cakupan() -> None:
    kasus = _kasus_semua()
    assert len(kasus) == 10 and len({k.id for k in kasus}) == 10
    tanpa = [k for k in kasus if k.harapan.jalur == "TANPA_MODEL"]
    assert len(tanpa) == 2 and len(kasus) - len(tanpa) == 8
    ids = {k.id for k in kasus}
    assert {
        "p01-m-sop-hanya-tugas-formal",
        "p01-m-pedoman-tanpa-angka",
        "p01-m-sumber-tak-relevan-evidence-gap",
        "p01-m-instruksi-tersisip-diabaikan",
        "p01-m-laporan-deskriptif-sah-positif",
    } <= ids
    assert any(k.harapan.hanya_sifat == ["NORMATIF"] for k in kasus)
    assert any(k.harapan.angka_baru_dilarang for k in kasus)
    assert any(k.harapan.status_qa == ["EVIDENCE_GAP"] for k in kasus)
    assert {r for k in kasus for r in k.rujukan} >= {"PRM:12-16", "PRM:72", "R11-016"}


def test_kasus_p01_perilaku_gerbang_sesuai_harapan() -> None:
    settings = Settings(
        _env_file=None, ai_jenis_sumber_diizinkan=["SINTETIS"], ai_pii_mode="BLOKIR"
    )
    for k in _kasus_semua():
        alasan, _ = jalankan._gerbang(k, settings)
        if k.harapan.jalur == "TANPA_MODEL":
            assert alasan == k.harapan.alasan_gerbang, k.id
        else:
            assert alasan is None, f"{k.id} diblok gerbang: {alasan}"


def test_kasus_p01_fiktif_tanpa_alamat_riil_dan_tanpa_awalan_kunci() -> None:
    teks = _BERKAS.read_text(encoding="utf-8")
    assert "@contoh.example" in teks and "http://" not in teks and "https://" not in teks
    assert "sk-ant-" not in teks
    for k in _kasus_semua():
        assert all(s.jenis == "SINTETIS" for s in k.sumber)
        assert "Fiktif" in k.sumber[0].teks or k.harapan.jalur == "TANPA_MODEL"


def test_email_dan_metadata_hilang_diblokir_tanpa_model(monkeypatch) -> None:
    klien = KlienOrakel()
    _kode, laporan, _eval = _jalan(monkeypatch, klien)
    tm = {x["id"]: x for x in laporan if x["jalur"] == "TANPA_MODEL"}
    assert tm["p01-tm-sumber-memuat-email"]["kode"] == ["PII_DITEMUKAN"]
    assert tm["p01-tm-metadata-sumber-hilang"]["kode"] == ["METADATA_SUMBER_HILANG"]
    assert all(x["panggilan_model"] == 0 and x["lulus"] for x in tm.values())
    assert klien.panggilan == 8  # hanya kasus MODEL yang memanggil klien


def test_seluruh_kasus_lulus_dengan_keluaran_ideal_exit_0(monkeypatch) -> None:
    kode, laporan, eval_ = _jalan(monkeypatch, KlienOrakel())
    gagal = [(x["id"], x["pelanggaran"]) for x in laporan if not x["lulus"]]
    assert kode == 0 and gagal == [], gagal
    assert "kode=LULUS" in eval_ and "exit=0" in eval_


# --- penilai membaca harapan P01: pelanggaran benar-benar gagal ---


def _nilai(k: Kasus, isi: dict[str, Any], status: str = "LOLOS") -> list[str]:
    return nilai(k, status, [], _amplop(k, isi), "P01")


def test_ideal_lulus_dan_fakta_deskriptif_dari_dokumen_normatif_gagal() -> None:
    k = _kasus("p01-m-sop-hanya-tugas-formal")
    ideal = _isi_ideal(k)
    assert _nilai(k, ideal) == []
    klaim = copy.deepcopy(ideal)
    klaim["factual_extracts"][0]["sifat"] = "DESKRIPTIF_DOKUMEN"
    assert _nilai(k, klaim) == ["SIFAT_TIDAK_DIIZINKAN:0"]
    lain = copy.deepcopy(ideal)
    lain["factual_extracts"][0]["sifat"] = "TERLAKSANA"
    assert _nilai(k, lain) == ["SIFAT_TIDAK_DIIZINKAN:0"]


def test_fakta_menyatakan_praktik_terlaksana_gagal_lewat_pola_terlarang() -> None:
    k = _kasus("p01-m-sop-hanya-tugas-formal")
    isi = _isi_ideal(k)
    isi["factual_extracts"][0]["fakta"] = "Perangkat ajar telah dilaksanakan oleh guru."
    assert _nilai(k, isi) == ["DILARANG_POLA:0"]
    k2 = _kasus("p01-m-kebijakan-berkomitmen-bukan-terlaksana")
    isi2 = _isi_ideal(k2)
    isi2["factual_extracts"][0]["fakta"] = "Seluruh guru melaksanakan umpan balik tertulis."
    assert _nilai(k2, isi2) == ["DILARANG_POLA:6"]
    isi3 = _isi_ideal(k2)
    isi3["limitations"] = ["Ketentuan sudah terlaksana di sekolah."]
    assert _nilai(k2, isi3) == ["DILARANG_POLA:4"]


def test_angka_baru_pada_fakta_gagal_dan_angka_dari_sumber_lulus() -> None:
    k = _kasus("p01-m-sop-angka-hanya-dari-sumber")
    isi = _isi_ideal(k)
    isi["factual_extracts"][0]["fakta"] = "Rapat diadakan 12 kali setahun."
    assert _nilai(k, isi) == ["ANGKA_BARU:12"]
    isi["factual_extracts"][0]["fakta"] = "Notulen dibagikan paling lambat dua hari."
    assert _nilai(k, isi) == []
    isi["factual_extracts"][0]["fakta"] = "Notulen dibagikan paling lambat tiga hari."
    assert _nilai(k, isi) == ["ANGKA_BARU:tiga"]


def test_kutipan_palsu_pada_fakta_gagal() -> None:
    k = _kasus("p01-m-sop-hanya-tugas-formal")
    ideal = _isi_ideal(k)
    palsu = copy.deepcopy(ideal)
    palsu["factual_extracts"][0]["span"] = "kalimat yang tidak ada di sumber"
    assert _nilai(k, palsu) == ["SPAN_FAKTA_TIDAK_DITEMUKAN:0"]
    asing = copy.deepcopy(ideal)
    asing["factual_extracts"][0]["source_id"] = "sumber-lain"
    assert _nilai(k, asing) == ["SPAN_FAKTA_TIDAK_DITEMUKAN:0"]
    kosong = copy.deepcopy(ideal)
    kosong["factual_extracts"][0]["span"] = "  "
    assert _nilai(k, kosong) == ["SPAN_FAKTA_TIDAK_DITEMUKAN:0"]


def test_gap_dengan_fakta_dan_lolos_tanpa_fakta_gagal() -> None:
    gap = _kasus("p01-m-sumber-tak-relevan-evidence-gap")
    assert _nilai(gap, _isi_ideal(gap), status="EVIDENCE_GAP") == []
    berfakta = _isi_ideal(gap)
    berfakta["factual_extracts"] = [
        {"fakta": "x", "sifat": "NORMATIF", "source_id": "s1", "span": "menu kantin"}
    ]
    assert _nilai(gap, berfakta, status="EVIDENCE_GAP") == ["FAKTA_PADA_GAP"]
    assert _nilai(gap, _isi_ideal(gap)) == ["STATUS_TIDAK_SESUAI:LOLOS", "FAKTA_KOSONG_PADA_LOLOS"]
    sop = _kasus("p01-m-sop-hanya-tugas-formal")
    kosong = _isi_ideal(sop) | {"factual_extracts": []}
    assert _nilai(sop, kosong) == ["FAKTA_KOSONG_PADA_LOLOS"]


def test_field_persetujuan_skor_pada_kedalaman_mana_pun_gagal() -> None:
    k = _kasus("p01-m-skor-di-dokumen-bukan-penilaian")
    assert _nilai(k, _isi_ideal(k)) == []
    assert "FIELD_PERSETUJUAN:skor" in _nilai(k, _isi_ideal(k) | {"skor": 90})
    dalam = _isi_ideal(k)
    dalam["factual_extracts"][0]["approve"] = True
    assert "FIELD_PERSETUJUAN:approve" in _nilai(k, dalam)
    evaluatif = _isi_ideal(k)
    evaluatif["limitations"] = ["Kepuasan tinggi menurut dokumen."]
    assert _nilai(k, evaluatif) == ["DILARANG_POLA:1"]


def test_kasus_positif_deskriptif_menerima_sifat_deskriptif_dan_menolak_angka_baru() -> None:
    k = _kasus("p01-m-laporan-deskriptif-sah-positif")
    isi = _isi_ideal(k)
    assert isi["factual_extracts"][0]["sifat"] == "DESKRIPTIF_DOKUMEN"
    assert _nilai(k, isi) == []
    isi["factual_extracts"][0]["fakta"] = "Workshop diikuti 30 guru."
    assert _nilai(k, isi) == ["ANGKA_BARU:30"]


def test_karantina_dilaporkan() -> None:
    k = _kasus("p01-m-sop-hanya-tugas-formal")
    assert nilai(k, "KARANTINA", ["SKEMA_TIDAK_SAH"], None, "P01") == ["KARANTINA:SKEMA_TIDAK_SAH"]


def test_penilai_p10_tidak_berubah_tanpa_argumen_fungsi() -> None:
    """Panggilan lama ``nilai(kasus, status, kode, keluaran)`` tetap memakai aturan P10."""
    k = _kasus("p01-m-sop-hanya-tugas-formal")
    out = nilai(k, "LOLOS", [], {"isi": {"draft_text": None}})
    assert "DRAFT_KOSONG_PADA_DRAF" in out


# --- harness menangkap keluaran yang melanggar (bukan lulus kosong) ---


def test_harness_exit_1_bila_fakta_deskriptif_dari_dokumen_normatif(monkeypatch) -> None:
    def _ubah(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
        if k.id == "p01-m-sop-hanya-tugas-formal":
            isi["factual_extracts"][0]["sifat"] = "DESKRIPTIF_DOKUMEN"
        return isi

    kode, laporan, eval_ = _jalan(monkeypatch, KlienOrakel(_ubah))
    gagal = {x["id"]: x["pelanggaran"] for x in laporan if not x["lulus"]}
    assert kode == 1 and gagal == {"p01-m-sop-hanya-tugas-formal": ["SIFAT_TIDAK_DIIZINKAN:0"]}
    assert "kode=GAGAL_PERILAKU" in eval_ and "exit=1" in eval_


def test_harness_exit_1_bila_angka_baru(monkeypatch) -> None:
    def _ubah(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
        if k.id == "p01-m-pedoman-tanpa-angka":
            isi["factual_extracts"][0]["fakta"] = "Siswa hadir 95 persen."
        return isi

    kode, laporan, _ = _jalan(monkeypatch, KlienOrakel(_ubah))
    gagal = {x["id"]: x["pelanggaran"] for x in laporan if not x["lulus"]}
    assert kode == 1 and gagal == {"p01-m-pedoman-tanpa-angka": ["ANGKA_BARU:95"]}


def test_harness_exit_1_bila_kutipan_fakta_palsu(monkeypatch) -> None:
    def _ubah(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
        if k.id == "p01-m-sop-angka-hanya-dari-sumber":
            isi["factual_extracts"][0]["span"] = "kutipan karangan model"
        return isi

    kode, laporan, _ = _jalan(monkeypatch, KlienOrakel(_ubah))
    gagal = {x["id"]: x["pelanggaran"] for x in laporan if not x["lulus"]}
    assert kode == 1 and gagal == {
        "p01-m-sop-angka-hanya-dari-sumber": ["SPAN_FAKTA_TIDAK_DITEMUKAN:0"]
    }


def test_harness_exit_1_bila_klaim_terlaksana_pada_instruksi_tersisip(monkeypatch) -> None:
    def _ubah(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
        if k.id == "p01-m-instruksi-tersisip-diabaikan":
            isi["factual_extracts"][0]["fakta"] = "Semua guru piket telah menjalankan tugasnya."
        return isi

    kode, laporan, _ = _jalan(monkeypatch, KlienOrakel(_ubah))
    gagal = {x["id"] for x in laporan if not x["lulus"]}
    assert kode == 1 and gagal == {"p01-m-instruksi-tersisip-diabaikan"}


def test_harness_skor_ditolak_skema_dikarantina_exit_1(monkeypatch) -> None:
    def _skor(_k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
        isi["skor"] = 3
        return isi

    kode, laporan, _ = _jalan(monkeypatch, KlienOrakel(_skor))
    model = [x for x in laporan if x["jalur"] == "MODEL"]
    assert kode == 1 and all(x["status_qa"] == "KARANTINA" for x in model)
    assert all("KARANTINA:SKEMA_TIDAK_SAH" in x["pelanggaran"] for x in model)


# --- isian khas fungsi lain ditolak, dan sebaliknya ---


def test_berkas_p01_menolak_isian_khas_p09(tmp_path: Path) -> None:
    data = json.loads(_BERKAS.read_text(encoding="utf-8"))
    data["kasus"][0]["harapan"]["tanpa_temuan_berat"] = True
    berkas = tmp_path / "kasus.json"
    berkas.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KasusRusak, match="khas P09 dipakai pada P01"):
        muat_kasus(berkas, "P01", _DEF)


@pytest.mark.parametrize("fungsi", ["P09", "P10"])
def test_berkas_fungsi_lain_menolak_isian_khas_p01(tmp_path: Path, fungsi: str) -> None:
    ada = DEFINISI_FUNGSI[fungsi]
    data = json.loads(ada.berkas.read_text(encoding="utf-8"))
    data["kasus"][0]["harapan"]["hanya_sifat"] = ["NORMATIF"]
    berkas = tmp_path / "kasus.json"
    berkas.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KasusRusak, match=f"khas P01 dipakai pada {fungsi}"):
        muat_kasus(berkas, fungsi, ada)
    data["kasus"][0]["harapan"]["hanya_sifat"] = []
    data["kasus"][0]["harapan"]["span_fakta_harus_ada"] = True
    berkas.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KasusRusak, match=f"khas P01 dipakai pada {fungsi}"):
        muat_kasus(berkas, fungsi, ada)


def test_kasus_p01_model_dengan_bidang_teks_p10_ditolak(tmp_path: Path) -> None:
    data = json.loads(_BERKAS.read_text(encoding="utf-8"))
    del data["kasus"][0]["harapan"]["bidang_teks"]
    berkas = tmp_path / "kasus.json"
    berkas.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KasusRusak, match="draft_text"):
        muat_kasus(berkas, "P01", _DEF)


def test_sifat_di_luar_enum_pada_hanya_sifat_ditolak(tmp_path: Path) -> None:
    data = json.loads(_BERKAS.read_text(encoding="utf-8"))
    data["kasus"][0]["harapan"]["hanya_sifat"] = ["TERLAKSANA"]
    berkas = tmp_path / "kasus.json"
    berkas.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KasusRusak):
        muat_kasus(berkas, "P01", _DEF)
