"""Uji harness evaluasi P05 (``evals/p05/kasus.json``) dengan klien tiruan: tanpa jaringan.

Yang dibuktikan: ``kasus.json`` lolos format harness, penilai khas P05 menagih status
hipotesis, penyangkal, dan rujukan, dan keluaran tiruan yang melanggar benar-benar gagal.
Perilaku MODEL sungguhan tidak terbukti di sini.
"""

from __future__ import annotations

import io
import json
from typing import Any

from anjab_abk_backend.ai.klien import JawabanModel
from evals import jalankan
from evals.kasus import DEFINISI_FUNGSI, Kasus, muat_kasus
from evals.penilai import nilai

_DEF = DEFINISI_FUNGSI["P05"]
_KUNCI_UJI = "kunci-uji-tiruan-p05h3"


def _kasus_semua() -> list[Kasus]:
    return muat_kasus(_DEF.berkas, "P05", _DEF)


def _isi_ideal(k: Kasus) -> dict[str, Any]:
    langkah = [s.source_id for s in k.sumber if s.source_id.startswith("langkah:")]
    return {
        "process_draft": {
            "langkah": [
                {"urutan": 1, "uraian": "Langkah pertama", "pelaksana": "Staf",
                 "source_ids": [langkah[0]]},
            ]
        },
        "issue_hypotheses": [
            {"hipotesis": "Dugaan hambatan di langkah pertama", "status": "HIPOTESIS",
             "source_ids": [k.sumber[0].source_id, langkah[0]]},
        ],
        "disconfirming_checks": [
            {"hipotesis_ke": 0, "pemeriksaan": "Bandingkan waktu tunggu antarlangkah",
             "data_dibutuhkan": "Catatan waktu tiap langkah"},
        ],
        "evidence_gaps": ["Waktu tunggu belum diukur"],
    }  # fmt: skip


def _keluaran(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
    s = k.sumber[0]
    return {
        "status": "AI_DRAFT",
        "source_refs": [],
        "cited_spans": [{"source_id": s.source_id, "span": s.teks.splitlines()[0]}],
        "confidence_reason": "alur tercatat",
        "unknowns": ["Waktu tunggu belum diukur."],
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
    argv = ["--fungsi", "P05", "--penyedia", "API_ANTHROPIC"]
    kode = jalankan.main(argv, {"ANTHROPIC_API_KEY": _KUNCI_UJI, "EVAL_ULANG": "1"}, out, err)
    return kode, out.getvalue().splitlines()[-1]


def test_kasus_p05_lolos_format_harness_dan_berjalur_campuran() -> None:
    kasus = _kasus_semua()
    assert len(kasus) >= 3
    assert {k.harapan.jalur for k in kasus} == {"MODEL", "TANPA_MODEL"}
    for k in kasus:
        assert k.sumber[0].source_id.startswith("masalah:")
        assert any(s.source_id.startswith("langkah:") for s in k.sumber)


def test_seluruh_kasus_lulus_dengan_keluaran_ideal_exit_0(monkeypatch) -> None:
    klien = KlienOrakel()
    kode, akhir = _jalan(monkeypatch, klien)
    assert kode == 0, akhir
    assert klien.panggilan == sum(1 for k in _kasus_semua() if k.harapan.jalur == "MODEL")


def test_penilai_menagih_status_penyangkal_dan_rujukan() -> None:
    k = next(k for k in _kasus_semua() if k.harapan.jalur == "MODEL")
    assert nilai(k, "LOLOS", [], _keluaran(k, _isi_ideal(k)), "P05") == []
    isi = _isi_ideal(k)
    isi["disconfirming_checks"] = []
    assert "HIPOTESIS_TANPA_PENYANGKAL:0" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P05")
    isi = _isi_ideal(k)
    isi["issue_hypotheses"][0]["status"] = "TERBUKTI"
    assert "STATUS_BUKAN_HIPOTESIS:0" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P05")
    isi = _isi_ideal(k)
    isi["issue_hypotheses"][0]["source_ids"].append("bukti:asing")
    pel = nilai(k, "LOLOS", [], _keluaran(k, isi), "P05")
    assert "RUJUKAN_TAK_DIKENAL:issue_hypotheses:0" in pel
    kosong = {**_isi_ideal(k), "issue_hypotheses": [], "disconfirming_checks": []}
    assert "HIPOTESIS_KOSONG_PADA_LOLOS" in nilai(k, "LOLOS", [], _keluaran(k, kosong), "P05")


def test_harness_exit_1_bila_hipotesis_tanpa_penyangkal(monkeypatch) -> None:
    klien = KlienOrakel(lambda _k, isi: {**isi, "disconfirming_checks": []})
    kode, _ = _jalan(monkeypatch, klien)
    assert kode == 1
