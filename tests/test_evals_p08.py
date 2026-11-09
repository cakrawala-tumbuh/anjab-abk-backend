"""Uji harness evaluasi P08 (``evals/p08/kasus.json``) dengan klien tiruan: tanpa jaringan.

Yang dibuktikan: ``kasus.json`` lolos format harness, penilai khas P08 menagih naskah,
keterbatasan, rujukan, klaim tanpa statistik, dan klaim terlarang, dan keluaran tiruan yang
melanggar benar-benar gagal. Perilaku MODEL sungguhan tidak terbukti di sini.
"""

from __future__ import annotations

import io
import json
from typing import Any

from anjab_abk_backend.ai.klien import JawabanModel
from evals import jalankan
from evals.kasus import DEFINISI_FUNGSI, Kasus, muat_kasus
from evals.penilai import nilai

_DEF = DEFINISI_FUNGSI["P08"]
_KUNCI_UJI = "kunci-uji-tiruan-p08s5"


def _kasus_semua() -> list[Kasus]:
    return muat_kasus(_DEF.berkas, "P08", _DEF)


def _isi_ideal(k: Kasus) -> dict[str, Any]:
    prot = k.sumber[0].source_id
    stat = [s.source_id for s in k.sumber if s.source_id.startswith("statistik:")]
    neg = [s.source_id for s in k.sumber if s.source_id.startswith("kasus-negatif:")]
    return {
        "manuscript_sections": [
            {"bagian": "METODE", "teks": "Analisis mengikuti protokol terkunci",
             "source_ids": [prot]},
            {"bagian": "HASIL", "teks": "Keluaran analisis dilaporkan apa adanya beserta kasus "
             "yang tidak mendukung", "source_ids": [*stat, *neg]},
        ],
        "evidence_table": [
            {"klaim": "Keluaran tercatat pada statistik", "statistik_ids": stat,
             "batasan": "Data sintetis satu periode"},
        ],
        "limitations": ["Sampel kecil"],
        "unsupported_claims": [],
    }  # fmt: skip


def _keluaran(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
    s = k.sumber[0]
    return {
        "status": "AI_DRAFT",
        "source_refs": [],
        "cited_spans": [{"source_id": s.source_id, "span": s.teks.splitlines()[0]}],
        "confidence_reason": "statistik terverifikasi tersedia",
        "unknowns": ["Generalisasi ke unit lain belum diketahui."],
        "contradictions": [],
        "human_review_required": True,
        "isi": isi,
    }


class KlienOrakel:
    """Klien tiruan: menjawab tiap kasus dari ``source_id`` sumber pertama pada masukan."""

    def __init__(self, ubah=None) -> None:
        self.ubah = ubah or (lambda _k, isi: isi)
        self.panggilan = 0
        self.per_sid = {k.sumber[0].source_id: k for k in _kasus_semua()}

    def panggil(self, instruksi: str, masukan_json: str, skema: dict[str, Any]) -> JawabanModel:
        self.panggilan += 1
        k = self.per_sid[json.loads(masukan_json)["sumber"][0]["source_id"]]
        isi = self.ubah(k, _isi_ideal(k))
        return JawabanModel(
            teks=json.dumps(_keluaran(k, isi)), model_dilayani="model-tiruan",
            stop_reason="end_turn", input_tokens=5, output_tokens=5,
        )  # fmt: skip


def _jalan(monkeypatch, klien) -> tuple[int, str]:
    monkeypatch.setattr(jalankan, "_tidur", lambda _d: None)
    monkeypatch.setattr(jalankan, "AnthropicKlienModel", lambda _s, **_kw: klien)
    out, err = io.StringIO(), io.StringIO()
    argv = ["--fungsi", "P08", "--penyedia", "API_ANTHROPIC"]
    kode = jalankan.main(argv, {"ANTHROPIC_API_KEY": _KUNCI_UJI, "EVAL_ULANG": "1"}, out, err)
    return kode, out.getvalue().splitlines()[-1]


def test_kasus_p08_lolos_format_harness_dan_berjalur_campuran() -> None:
    kasus = _kasus_semua()
    assert len(kasus) >= 3
    assert {k.harapan.jalur for k in kasus} == {"MODEL", "TANPA_MODEL"}
    for k in kasus:
        assert k.sumber[0].source_id.startswith("protokol:")
        assert any(s.source_id.startswith("statistik:") for s in k.sumber)
        assert any(s.source_id.startswith("kasus-negatif:") for s in k.sumber)


def test_seluruh_kasus_lulus_dengan_keluaran_ideal_exit_0(monkeypatch) -> None:
    klien = KlienOrakel()
    kode, akhir = _jalan(monkeypatch, klien)
    assert kode == 0, akhir
    assert klien.panggilan == sum(1 for k in _kasus_semua() if k.harapan.jalur == "MODEL")


def test_penilai_menagih_naskah_rujukan_statistik_dan_klaim_terlarang() -> None:
    k = next(k for k in _kasus_semua() if k.harapan.jalur == "MODEL")
    assert nilai(k, "LOLOS", [], _keluaran(k, _isi_ideal(k)), "P08") == []
    isi = _isi_ideal(k)
    isi["evidence_table"][0]["statistik_ids"] = [k.sumber[0].source_id]
    assert "KLAIM_TANPA_STATISTIK" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P08")
    isi = _isi_ideal(k)
    isi["manuscript_sections"][1]["source_ids"] = [k.sumber[0].source_id]
    assert "HASIL_TANPA_STATISTIK" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P08")
    isi = _isi_ideal(k)
    isi["manuscript_sections"][0]["teks"] = "Hasil signifikan"
    assert "KLAIM_TERLARANG" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P08")
    kosong = {**_isi_ideal(k), "manuscript_sections": []}
    assert "NASKAH_KOSONG_PADA_LOLOS" in nilai(k, "LOLOS", [], _keluaran(k, kosong), "P08")


def test_harness_exit_1_bila_ada_klaim_q1(monkeypatch) -> None:
    def _ubah(_k, isi):
        isi["manuscript_sections"][0]["teks"] = "Layak terbit di jurnal Q1"
        return isi

    kode, _ = _jalan(monkeypatch, KlienOrakel(_ubah))
    assert kode == 1
