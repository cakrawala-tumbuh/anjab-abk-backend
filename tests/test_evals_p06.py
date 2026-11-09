"""Uji harness evaluasi P06 (``evals/p06/kasus.json``) dengan klien tiruan: tanpa jaringan.

Yang dibuktikan: ``kasus.json`` lolos format harness, penilai khas P06 menagih opsi, rujukan,
kata status terlarang, dan angka FTE, dan keluaran tiruan yang melanggar benar-benar gagal.
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

_DEF = DEFINISI_FUNGSI["P06"]
_KUNCI_UJI = "kunci-uji-tiruan-p06o4"


def _kasus_semua() -> list[Kasus]:
    return muat_kasus(_DEF.berkas, "P06", _DEF)


def _isi_ideal(k: Kasus) -> dict[str, Any]:
    alt = [s.source_id for s in k.sumber if s.source_id.startswith("alternatif:")]
    return {
        "options": [
            {"jenis": "SIMPLIFY", "opsi_aplikasi": "Sederhanakan",
             "uraian": "Satukan langkah yang berulang",
             "fakta_sumber": [{"pernyataan": "Langkah tercatat berulang",
                               "source_ids": [k.sumber[0].source_id, *alt]}],
             "asumsi": ["Pelaksana bersedia mengubah kebiasaan"]},
        ],
        "scenario_assumptions": ["Beban kerja penerima belum diketahui"],
        "unknown_parameters": [{"parameter": "Waktu tiap langkah", "alasan": "Belum diukur"}],
        "risks": [{"risiko": "Layanan tertunda saat transisi", "opsi_ke": 0}],
        "checks": [{"pemeriksaan": "Uji pada satu unit", "opsi_ke": 0}],
    }  # fmt: skip


def _keluaran(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
    s = k.sumber[0]
    return {
        "status": "AI_DRAFT",
        "source_refs": [],
        "cited_spans": [{"source_id": s.source_id, "span": s.teks.splitlines()[0]}],
        "confidence_reason": "alternatif tercatat",
        "unknowns": ["Waktu tiap langkah belum diukur."],
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
    argv = ["--fungsi", "P06", "--penyedia", "API_ANTHROPIC"]
    kode = jalankan.main(argv, {"ANTHROPIC_API_KEY": _KUNCI_UJI, "EVAL_ULANG": "1"}, out, err)
    return kode, out.getvalue().splitlines()[-1]


def test_kasus_p06_lolos_format_harness_dan_berjalur_campuran() -> None:
    kasus = _kasus_semua()
    assert len(kasus) >= 3
    assert {k.harapan.jalur for k in kasus} == {"MODEL", "TANPA_MODEL"}
    for k in kasus:
        assert k.sumber[0].source_id.startswith("masalah:")
        assert any(s.source_id.startswith("alternatif:") for s in k.sumber)


def test_seluruh_kasus_lulus_dengan_keluaran_ideal_exit_0(monkeypatch) -> None:
    klien = KlienOrakel()
    kode, akhir = _jalan(monkeypatch, klien)
    assert kode == 0, akhir
    assert klien.panggilan == sum(1 for k in _kasus_semua() if k.harapan.jalur == "MODEL")


def test_penilai_menagih_opsi_rujukan_status_dan_fte() -> None:
    k = next(k for k in _kasus_semua() if k.harapan.jalur == "MODEL")
    assert nilai(k, "LOLOS", [], _keluaran(k, _isi_ideal(k)), "P06") == []
    isi = _isi_ideal(k)
    isi["options"][0]["fakta_sumber"][0]["source_ids"] = ["bukti:asing"]
    assert "RUJUKAN_TAK_DIKENAL:options:0:0" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P06")
    isi = {**_isi_ideal(k), "scenario_assumptions": ["Penerima butuh 1,5 FTE"]}
    assert "ANGKA_FTE" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P06")
    isi = {**_isi_ideal(k), "scenario_assumptions": ["Opsi READY"]}
    assert "STATUS_TERLARANG" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P06")
    kosong = {**_isi_ideal(k), "options": []}
    assert "OPSI_KOSONG_PADA_LOLOS" in nilai(k, "LOLOS", [], _keluaran(k, kosong), "P06")


def test_harness_exit_1_bila_ada_angka_fte(monkeypatch) -> None:
    klien = KlienOrakel(lambda _k, isi: {**isi, "scenario_assumptions": ["Tambah 2 FTE"]})
    kode, _ = _jalan(monkeypatch, klien)
    assert kode == 1
