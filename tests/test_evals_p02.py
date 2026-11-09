"""Uji harness evaluasi P02 (``evals/p02/kasus.json``) dengan klien tiruan: tanpa jaringan.

Yang dibuktikan: ``kasus.json`` lolos format harness, penilai khas P02 membaca kandidat dan
rujukan sumber, dan keluaran tiruan yang melanggar benar-benar gagal. Perilaku MODEL sungguhan
tidak terbukti di sini.
"""

from __future__ import annotations

import io
import json
from typing import Any

from anjab_abk_backend.ai.klien import JawabanModel
from evals import jalankan
from evals.kasus import DEFINISI_FUNGSI, Kasus, muat_kasus
from evals.penilai import nilai

_DEF = DEFINISI_FUNGSI["P02"]
_KUNCI_UJI = "kunci-uji-tiruan-p02q7"


def _kasus_semua() -> list[Kasus]:
    return muat_kasus(_DEF.berkas, "P02", _DEF)


def _isi_ideal(k: Kasus) -> dict[str, Any]:
    ids = [s.source_id for s in k.sumber]
    return {
        "task_candidates": [
            {
                "tindakan": "Menyusun",
                "objek": "dokumen",
                "tujuan": "tertib administrasi",
                "cara": "mengikuti format",
                "output": "dokumen tersusun",
                "tingkat": "TASK",
                "source_ids": [ids[0]],
            }
        ],  # fmt: skip
        "duplicate_suspicions": [{"source_ids": ids[:2], "alasan": "objek mirip"}]
        if len(ids) >= 2
        else [],
        "split_merge_rationale": [],
        "reviewer_questions": ["Apakah kedua uraian dikerjakan orang yang sama?"],
    }


def _amplop(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
    s = k.sumber[0]
    return {
        "status": "AI_DRAFT",
        "source_refs": [],
        "cited_spans": [{"source_id": s.source_id, "span": s.teks.splitlines()[0]}],
        "confidence_reason": "kutipan",
        "unknowns": [],
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
            teks=json.dumps(_amplop(k, isi)), model_dilayani="model-tiruan",
            stop_reason="end_turn", input_tokens=5, output_tokens=5,
        )  # fmt: skip


def _jalan(monkeypatch, klien) -> tuple[int, str]:
    monkeypatch.setattr(jalankan, "_tidur", lambda _d: None)
    monkeypatch.setattr(jalankan, "AnthropicKlienModel", lambda _s, **_kw: klien)
    out, err = io.StringIO(), io.StringIO()
    argv = ["--fungsi", "P02", "--penyedia", "API_ANTHROPIC"]
    kode = jalankan.main(argv, {"ANTHROPIC_API_KEY": _KUNCI_UJI, "EVAL_ULANG": "1"}, out, err)
    return kode, out.getvalue().splitlines()[-1]


def test_kasus_p02_lolos_format_harness_dan_berjalur_campuran() -> None:
    kasus = _kasus_semua()
    assert len(kasus) >= 3
    jalur = {k.harapan.jalur for k in kasus}
    assert jalur == {"MODEL", "TANPA_MODEL"}
    for k in kasus:
        assert all(s.source_id.startswith("uraian:") for s in k.sumber)


def test_seluruh_kasus_lulus_dengan_keluaran_ideal_exit_0(monkeypatch) -> None:
    klien = KlienOrakel()
    kode, akhir = _jalan(monkeypatch, klien)
    assert kode == 0, akhir
    assert klien.panggilan == sum(1 for k in _kasus_semua() if k.harapan.jalur == "MODEL")


def test_rujukan_asing_dan_kandidat_kosong_gagal() -> None:
    k = next(k for k in _kasus_semua() if k.harapan.jalur == "MODEL")
    isi = _isi_ideal(k)
    assert nilai(k, "LOLOS", [], {"isi": isi}, "P02") == []
    isi["task_candidates"][0]["source_ids"] = ["uraian:asing"]
    assert "RUJUKAN_TAK_DIKENAL:task_candidates:0" in nilai(k, "LOLOS", [], {"isi": isi}, "P02")
    kosong = {**_isi_ideal(k), "task_candidates": []}
    assert "KANDIDAT_KOSONG_PADA_LOLOS" in nilai(k, "LOLOS", [], {"isi": kosong}, "P02")


def test_harness_exit_1_bila_field_persetujuan(monkeypatch) -> None:
    klien = KlienOrakel(lambda _k, isi: {**isi, "skor": 5})
    kode, _ = _jalan(monkeypatch, klien)
    assert kode == 1
