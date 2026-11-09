"""Uji harness evaluasi P03 terbatas (``evals/p03/kasus.json``) dengan klien tiruan: tanpa jaringan.

Yang dibuktikan: ``kasus.json`` lolos format harness, penilai khas P03 menagih dasar mandat,
status aktual, rujukan, dan ``unknowns``, dan keluaran tiruan yang melanggar benar-benar gagal.
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

_DEF = DEFINISI_FUNGSI["P03"]
_KUNCI_UJI = "kunci-uji-tiruan-p03q7"


def _kasus_semua() -> list[Kasus]:
    return muat_kasus(_DEF.berkas, "P03", _DEF)


def _isi_ideal(k: Kasus) -> dict[str, Any]:
    mandat = [s.source_id for s in k.sumber if s.source_id.startswith("uraian:")]
    return {
        "tag_candidates": [
            {
                "kandidat_ke": 0,
                "jabatan_kode": k.parameter["jabatan_kode"],
                "dasar": "MANDAT_FORMAL",
                "status_aktual": "BELUM_DIKETAHUI",
                "source_ids": [k.sumber[0].source_id, mandat[0]],
            }
        ],
        "owner_ambiguities": [],
    }


def _keluaran(k: Kasus, isi: dict[str, Any], unknowns: list[str] | None = None) -> dict[str, Any]:
    s = k.sumber[1]
    return {
        "status": "AI_DRAFT",
        "source_refs": [],
        "cited_spans": [{"source_id": s.source_id, "span": s.teks.splitlines()[0]}],
        "confidence_reason": "mandat formal",
        "unknowns": ["Sumber penugasan aktual tidak tersedia."] if unknowns is None else unknowns,
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
    argv = ["--fungsi", "P03", "--penyedia", "API_ANTHROPIC"]
    kode = jalankan.main(argv, {"ANTHROPIC_API_KEY": _KUNCI_UJI, "EVAL_ULANG": "1"}, out, err)
    return kode, out.getvalue().splitlines()[-1]


def test_kasus_p03_lolos_format_harness_dan_berjalur_campuran() -> None:
    kasus = _kasus_semua()
    assert len(kasus) >= 3
    assert {k.harapan.jalur for k in kasus} == {"MODEL", "TANPA_MODEL"}
    for k in kasus:
        assert k.sumber[0].source_id.startswith("usulan:")
        assert all(s.source_id.startswith("uraian:") for s in k.sumber[1:])


def test_seluruh_kasus_lulus_dengan_keluaran_ideal_exit_0(monkeypatch) -> None:
    klien = KlienOrakel()
    kode, akhir = _jalan(monkeypatch, klien)
    assert kode == 0, akhir
    assert klien.panggilan == sum(1 for k in _kasus_semua() if k.harapan.jalur == "MODEL")


def test_penilai_menagih_mandat_status_aktual_rujukan_dan_unknowns() -> None:
    k = next(k for k in _kasus_semua() if k.harapan.jalur == "MODEL")
    assert nilai(k, "LOLOS", [], _keluaran(k, _isi_ideal(k)), "P03") == []
    isi = _isi_ideal(k)
    isi["tag_candidates"][0]["source_ids"] = [k.sumber[0].source_id]
    assert "TANPA_DASAR_MANDAT:0" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P03")
    isi = _isi_ideal(k)
    isi["tag_candidates"][0]["status_aktual"] = "AKTUAL"
    assert "STATUS_AKTUAL_DINYATAKAN:0" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P03")
    isi = _isi_ideal(k)
    isi["tag_candidates"][0]["source_ids"].append("uraian:asing@jbt_x")
    pel = nilai(k, "LOLOS", [], _keluaran(k, isi), "P03")
    assert "RUJUKAN_TAK_DIKENAL:tag_candidates:0" in pel
    assert "UNKNOWNS_KOSONG" in nilai(k, "LOLOS", [], _keluaran(k, _isi_ideal(k), []), "P03")
    kosong = {**_isi_ideal(k), "tag_candidates": []}
    assert "TAG_KOSONG_PADA_LOLOS" in nilai(k, "LOLOS", [], _keluaran(k, kosong), "P03")


def test_harness_exit_1_bila_field_persetujuan(monkeypatch) -> None:
    klien = KlienOrakel(lambda _k, isi: {**isi, "skor": 5})
    kode, _ = _jalan(monkeypatch, klien)
    assert kode == 1
