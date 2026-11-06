"""Uji harness evaluasi P09 (``evals/p09/kasus.json``) dengan klien tiruan: tanpa jaringan.

Yang dibuktikan: ``kasus.json`` lolos format harness, penilai MEMBACA ``harapan`` bentuk P09
(kategori temuan, draf bersih, span, tanpa field persetujuan), dan keluaran tiruan yang
melanggar benar-benar gagal. Perilaku MODEL sungguhan tidak terbukti di sini.
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

_DEF = DEFINISI_FUNGSI["P09"]
_BERKAS = _DEF.berkas
_KUNCI_UJI = "kunci-uji-tiruan-p09z4"


def _kasus_semua() -> list[Kasus]:
    return muat_kasus(_BERKAS, "P09", _DEF)


def _kasus(id_: str) -> Kasus:
    return next(k for k in _kasus_semua() if k.id == id_)


def _draf(k: Kasus):
    return next(s for s in k.sumber if s.source_id.startswith("versi:"))


def _isi_ideal(k: Kasus) -> dict[str, Any]:
    """Isi yang memenuhi ``harapan`` kasus ``k`` (dibangun dari harapannya sendiri)."""
    h = k.harapan
    temuan: list[dict[str, str]] = []
    if not h.tanpa_temuan_berat:
        asal = next(s for s in k.sumber if not s.source_id.startswith("versi:"))
        potongan = " ".join(asal.teks.split()[:3])
        for pilihan in h.kategori_wajib:
            kat = pilihan if isinstance(pilihan, str) else pilihan[0]
            temuan.append(
                {"temuan": "perlu diperiksa", "kategori": kat, "source_id": asal.source_id,
                 "span": potongan}
            )  # fmt: skip
    return {
        "peran": "REVIEWER_OTOMATIS_PEMBANTU",
        "blocking_findings": temuan,
        "major_findings": [],
        "correction_proposals": [],
        "limitations": ["tidak memeriksa makna parafrasa"],
    }


def _amplop(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
    draf = _draf(k)
    return {
        "status": "AI_DRAFT",
        "source_refs": [],
        "cited_spans": [{"source_id": draf.source_id, "span": " ".join(draf.teks.split()[:3])}],
        "confidence_reason": "kutipan",
        "unknowns": [],
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
    """Klien tiruan: menjawab tiap kasus dari ``narasi_versi_id`` pada masukan."""

    def __init__(self, ubah=None) -> None:
        self.ubah = ubah or (lambda _k, isi: isi)
        self.panggilan = 0
        self.per_versi = {k.parameter["narasi_versi_id"]: k for k in _kasus_semua()}

    def panggil(self, instruksi: str, masukan_json: str, skema: dict[str, Any]) -> JawabanModel:
        self.panggilan += 1
        k = self.per_versi[json.loads(masukan_json)["parameter"]["narasi_versi_id"]]
        isi = self.ubah(k, _isi_ideal(k))
        return _jawab(json.dumps(_amplop(k, isi)))


def _jalan(monkeypatch, klien, argv_extra=None) -> tuple[int, list[dict[str, Any]], str]:
    monkeypatch.setattr(jalankan, "_tidur", lambda _d: None)
    monkeypatch.setattr(jalankan, "AnthropicKlienModel", lambda _s, **_kw: klien)
    out, err = io.StringIO(), io.StringIO()
    argv = ["--fungsi", "P09", "--penyedia", "API_ANTHROPIC", *(argv_extra or [])]
    kode = jalankan.main(argv, {"ANTHROPIC_API_KEY": _KUNCI_UJI, "EVAL_ULANG": "1"}, out, err)
    baris = out.getvalue().splitlines()
    assert baris[-1].startswith("#EVAL ")
    return kode, [json.loads(b) for b in baris[:-1]], baris[-1]


# --- berkas kasus ---


def test_kasus_p09_lolos_format_harness_jumlah_dan_cakupan() -> None:
    kasus = _kasus_semua()
    assert len(kasus) == 12 and len({k.id for k in kasus}) == 12
    tanpa = [k for k in kasus if k.harapan.jalur == "TANPA_MODEL"]
    assert len(tanpa) == 2 and len(kasus) - len(tanpa) == 10
    kategori = {c if isinstance(c, str) else c[0] for k in kasus for c in k.harapan.kategori_wajib}
    assert {"KLAIM_TANPA_DASAR", "SALAH_TAUTAN", "PENGHILANGAN", "PRIVASI"} <= kategori
    assert any(k.harapan.tanpa_temuan_berat for k in kasus)  # draf bersih
    assert {r for k in kasus for r in k.rujukan} >= {"PRM:60-64", "PRM:71", "PRM:91-6", "R11-016"}


def test_kasus_p09_memasukkan_draf_sebagai_sumber_versi_dan_parameter_cocok() -> None:
    for k in _kasus_semua():
        draf = _draf(k)
        assert draf.source_id == f"versi:{k.parameter['narasi_versi_id']}", k.id
        assert k.sumber[-1] is draf  # draf terakhir, seperti rute


def test_kasus_p09_perilaku_gerbang_sesuai_harapan() -> None:
    settings = Settings(
        _env_file=None, ai_jenis_sumber_diizinkan=["SINTETIS"], ai_pii_mode="BLOKIR"
    )
    for k in _kasus_semua():
        alasan, _ = jalankan._gerbang(k, settings)
        if k.harapan.jalur == "TANPA_MODEL":
            assert alasan == k.harapan.alasan_gerbang, k.id
        else:
            assert alasan is None, f"{k.id} diblok gerbang: {alasan}"


def test_kasus_p09_fiktif_tanpa_alamat_riil_dan_tanpa_awalan_kunci() -> None:
    teks = _BERKAS.read_text(encoding="utf-8")
    assert "@contoh.example" in teks and "http://" not in teks and "https://" not in teks
    assert "sk-ant-" not in teks
    for k in _kasus_semua():
        assert all(s.jenis == "SINTETIS" or k.harapan.jalur == "TANPA_MODEL" for s in k.sumber)


def test_draf_dengan_email_dan_jenis_campuran_diblokir_tanpa_model(monkeypatch) -> None:
    klien = KlienOrakel()
    kode, laporan, eval_ = _jalan(monkeypatch, klien)
    tm = {x["id"]: x for x in laporan if x["jalur"] == "TANPA_MODEL"}
    assert tm["p09-tm-draf-memuat-email"]["kode"] == ["PII_DITEMUKAN"]
    assert tm["p09-tm-sumber-jenis-campuran"]["kode"] == ["JENIS_DITOLAK"]
    assert all(x["panggilan_model"] == 0 and x["lulus"] for x in tm.values())
    assert klien.panggilan == 10  # hanya kasus MODEL yang memanggil klien


def test_seluruh_kasus_lulus_dengan_keluaran_ideal_exit_0(monkeypatch) -> None:
    kode, laporan, eval_ = _jalan(monkeypatch, KlienOrakel())
    gagal = [(x["id"], x["pelanggaran"]) for x in laporan if not x["lulus"]]
    assert kode == 0 and gagal == [], gagal
    assert "kode=LULUS" in eval_ and "exit=0" in eval_


# --- penilai membaca harapan P09: pelanggaran benar-benar gagal ---


def _nilai(k: Kasus, isi: dict[str, Any], status: str = "LOLOS") -> list[str]:
    return nilai(k, status, [], _amplop(k, isi), "P09")


def test_ideal_lulus_dan_pelanggaran_dilaporkan_per_jenis() -> None:
    k = _kasus("p09-m-klaim-tanpa-dasar")
    ideal = _isi_ideal(k)
    assert _nilai(k, ideal) == []

    salah = copy.deepcopy(ideal)
    salah["blocking_findings"][0]["kategori"] = "BIAS_PROMPT"
    assert _nilai(k, salah) == ["KATEGORI_WAJIB_HILANG:0"]

    kosong = copy.deepcopy(ideal) | {"blocking_findings": []}
    assert _nilai(k, kosong) == ["KATEGORI_WAJIB_HILANG:0"]

    span_palsu = copy.deepcopy(ideal)
    span_palsu["blocking_findings"][0]["span"] = "kalimat yang tidak ada di sumber"
    assert _nilai(k, span_palsu) == ["SPAN_TEMUAN_TIDAK_DITEMUKAN:0"]
    asing = copy.deepcopy(ideal)
    asing["blocking_findings"][0]["source_id"] = "sumber-lain"
    assert _nilai(k, asing) == ["SPAN_TEMUAN_TIDAK_DITEMUKAN:0"]

    menyetujui = copy.deepcopy(ideal)
    menyetujui["limitations"] = ["Draf ini disetujui untuk diteruskan."]
    assert _nilai(k, menyetujui) == ["DILARANG_POLA:0"]

    assert _nilai(k, ideal, status="EVIDENCE_GAP") == ["STATUS_TIDAK_SESUAI:EVIDENCE_GAP"]


def test_field_persetujuan_skor_pada_kedalaman_mana_pun_gagal() -> None:
    k = _kasus("p09-m-klaim-tanpa-dasar")
    atas = _isi_ideal(k) | {"skor": 90}
    assert "FIELD_PERSETUJUAN:skor" in _nilai(k, atas)
    dalam = _isi_ideal(k)
    dalam["blocking_findings"][0]["approve"] = True
    assert "FIELD_PERSETUJUAN:approve" in _nilai(k, dalam)
    assert "PERAN_SALAH" in _nilai(k, _isi_ideal(k) | {"peran": "PENYETUJU"})


def test_draf_bersih_dengan_temuan_berat_gagal() -> None:
    k = _kasus("p09-m-draf-bersih")
    assert _nilai(k, _isi_ideal(k)) == []
    isi = _isi_ideal(k)
    isi["major_findings"] = [
        {"temuan": "mengada-ada", "kategori": "PRIVASI", "source_id": "s1",
         "span": "guru menyusun"}
    ]  # fmt: skip
    assert "TEMUAN_PADA_DRAF_BERSIH" in _nilai(k, isi)


def test_karantina_dilaporkan_dan_alternatif_kategori_salah_satu_cukup() -> None:
    k = _kasus("p09-m-salah-tautan")
    assert nilai(k, "KARANTINA", ["SKEMA_TIDAK_SAH"], None, "P09") == ["KARANTINA:SKEMA_TIDAK_SAH"]
    isi = _isi_ideal(k)
    isi["blocking_findings"][0]["kategori"] = "KLAIM_TANPA_DASAR"  # alternatif kedua
    assert _nilai(k, isi) == []


def test_penilai_p10_tidak_berubah_tanpa_argumen_fungsi() -> None:
    """Panggilan lama ``nilai(kasus, status, kode, keluaran)`` tetap memakai aturan P10."""
    k = _kasus("p09-m-klaim-tanpa-dasar")
    out = nilai(k, "LOLOS", [], {"isi": {"draft_text": None}})
    assert "DRAFT_KOSONG_PADA_DRAF" in out


# --- harness menangkap keluaran yang melanggar ---


def test_harness_gagal_exit_1_bila_model_menyetujui_atau_menambah_skor(monkeypatch) -> None:
    def _ubah(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
        if k.id == "p09-m-draf-bersih":
            isi["limitations"] = ["Draf ini disetujui."]
        return isi

    kode, laporan, eval_ = _jalan(monkeypatch, KlienOrakel(_ubah))
    gagal = {x["id"] for x in laporan if not x["lulus"]}
    assert kode == 1 and gagal == {"p09-m-draf-bersih"}
    assert "kode=GAGAL_PERILAKU" in eval_ and "exit=1" in eval_

    def _skor(_k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
        isi["skor"] = 3
        return isi

    kode2, laporan2, _ = _jalan(monkeypatch, KlienOrakel(_skor))
    karantina = [x for x in laporan2 if x["jalur"] == "MODEL"]
    assert kode2 == 1 and all(x["status_qa"] == "KARANTINA" for x in karantina)
    assert all("KARANTINA:SKEMA_TIDAK_SAH" in x["pelanggaran"] for x in karantina)


def test_berkas_p10_menolak_isian_khas_p09(tmp_path: Path) -> None:
    from evals.kasus import DEFINISI_FUNGSI as DEF

    data = json.loads(DEF["P10"].berkas.read_text(encoding="utf-8"))
    data["kasus"][4]["harapan"]["tanpa_temuan_berat"] = True
    berkas = tmp_path / "kasus.json"
    berkas.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KasusRusak, match="khas P09"):
        muat_kasus(berkas, "P10", DEF["P10"])


def test_kasus_p09_model_dengan_bidang_teks_p10_ditolak(tmp_path: Path) -> None:
    data = json.loads(_BERKAS.read_text(encoding="utf-8"))
    del data["kasus"][0]["harapan"]["bidang_teks"]
    berkas = tmp_path / "kasus.json"
    berkas.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(KasusRusak, match="draft_text"):
        muat_kasus(berkas, "P09", _DEF)
