"""Uji harness evaluasi P11 (``evals/p11/kasus.json``) dengan klien tiruan: tanpa jaringan.

Yang dibuktikan: ``kasus.json`` lolos format harness, penilai khas P11 menagih kandidat minimum,
rujukan, ``mirip_kode``, dan jumlah kandidat terhadap parameter kasus, dan keluaran tiruan yang
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

_DEF = DEFINISI_FUNGSI["P11"]
_KUNCI_UJI = "kunci-uji-tiruan-p11k3"


def _kasus_semua() -> list[Kasus]:
    return muat_kasus(_DEF.berkas, "P11", _DEF)


def _isi_ideal(k: Kasus) -> dict[str, Any]:
    konteks = [s.source_id for s in k.sumber if s.source_id.startswith("konteks:")]
    return {
        "konteks_candidates": [
            {"tema": "Penyamaan format data antarunit",
             "ruang_dugaan": "Data yang sama dicatat ulang di beberapa tempat.",
             "sumber_draft": "Diturunkan dari konteks dan masalah pada sumber.",
             "batas_pemeriksaan": "Jam kerja yang terpakai belum diukur.",
             "gelombang_saran": "Belum dijadwalkan",
             "mirip_kode": k.parameter["kode_konteks_ada"][0],
             "source_ids": konteks[:1]},
        ],
        "reviewer_questions": ["Apakah pencatatan ulang ditetapkan kebijakan yayasan?"],
    }  # fmt: skip


def _keluaran(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
    s = k.sumber[0]
    return {
        "status": "AI_DRAFT",
        "source_refs": [],
        "cited_spans": [{"source_id": s.source_id, "span": s.teks.splitlines()[0]}],
        "confidence_reason": "katalog konteks tersedia",
        "unknowns": ["Besaran beban kerja belum diketahui."],
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
    argv = ["--fungsi", "P11", "--penyedia", "API_ANTHROPIC"]
    kode = jalankan.main(argv, {"ANTHROPIC_API_KEY": _KUNCI_UJI, "EVAL_ULANG": "1"}, out, err)
    return kode, out.getvalue().splitlines()[-1]


def test_kasus_p11_lolos_format_harness_dan_berjalur_campuran() -> None:
    kasus = _kasus_semua()
    assert len(kasus) >= 3
    assert {k.harapan.jalur for k in kasus} == {"MODEL", "TANPA_MODEL"}
    for k in kasus:
        assert k.sumber[0].source_id.startswith("konteks:")
        assert any(s.source_id.startswith("masalah:") for s in k.sumber)
        assert k.parameter["kode_konteks_ada"]


def test_seluruh_kasus_lulus_dengan_keluaran_ideal_exit_0(monkeypatch) -> None:
    klien = KlienOrakel()
    kode, akhir = _jalan(monkeypatch, klien)
    assert kode == 0, akhir
    assert klien.panggilan == sum(1 for k in _kasus_semua() if k.harapan.jalur == "MODEL")


def test_penilai_menagih_kandidat_rujukan_kode_dan_jumlah() -> None:
    k = next(k for k in _kasus_semua() if k.harapan.jalur == "MODEL")
    assert nilai(k, "LOLOS", [], _keluaran(k, _isi_ideal(k)), "P11") == []
    isi = _isi_ideal(k)
    isi["konteks_candidates"][0]["source_ids"] = ["konteks:asing"]
    assert "RUJUKAN_TAK_DIKENAL" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P11")
    isi = _isi_ideal(k)
    isi["konteks_candidates"][0]["mirip_kode"] = "K-99"
    assert "KODE_KONTEKS_TAK_DIKENAL" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P11")
    isi = _isi_ideal(k)
    isi["konteks_candidates"] *= k.parameter["jumlah_kandidat"] + 1
    assert "KANDIDAT_BERLEBIH" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P11")
    kosong = {**_isi_ideal(k), "konteks_candidates": []}
    assert "KANDIDAT_KOSONG_PADA_LOLOS" in nilai(k, "LOLOS", [], _keluaran(k, kosong), "P11")


def test_harness_exit_1_bila_kandidat_menyatakan_terbukti(monkeypatch) -> None:
    def _ubah(_k, isi):
        isi["konteks_candidates"][0]["ruang_dugaan"] = "Penyebabnya sudah terbukti."
        return isi

    kode, _ = _jalan(monkeypatch, KlienOrakel(_ubah))
    assert kode == 1
