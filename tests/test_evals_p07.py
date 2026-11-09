"""Uji harness evaluasi P07 (``evals/p07/kasus.json``) dengan klien tiruan: tanpa jaringan.

Yang dibuktikan: ``kasus.json`` lolos format harness, penilai khas P07 menagih isi kartu,
rujukan, kata status terlarang, signoff ``CHANGE``, dan nama field ``authorization_state``, dan
keluaran tiruan yang melanggar benar-benar gagal.
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

_DEF = DEFINISI_FUNGSI["P07"]
_KUNCI_UJI = "kunci-uji-tiruan-p07k2"


def _kasus_semua() -> list[Kasus]:
    return muat_kasus(_DEF.berkas, "P07", _DEF)


def _isi_ideal(k: Kasus) -> dict[str, Any]:
    ids = [s.source_id for s in k.sumber]
    alt = [i for i in ids if i.startswith("alternatif:")]
    bukti = [i for i in ids if i.startswith(("bukti:", "masalah:"))]
    return {
        "decision_card": {
            "masalah": "Keterlambatan proses tercatat pada sumber",
            "bukti": [{"pernyataan": "Keterlambatan tercatat", "source_ids": bukti}],
            "alternatif": [{"ringkasan": "Alternatif tercatat", "source_ids": [a]} for a in alt],
            "batas_angka": "Waktu tiap langkah belum diukur",
            "risiko": ["Layanan tertunda saat transisi"],
            "persyaratan": ["Uji pada satu unit lebih dulu"],
        },
        "limitation": ["Penerima tugas lengkap belum tercatat"],
        "required_signoffs": [
            {"jenis": "PRIORITY", "pihak": "Yayasan", "status": "BELUM_DITANDATANGANI"},
            {"jenis": "CHANGE", "pihak": "Yayasan", "status": "BELUM_DITANDATANGANI"},
        ],
    }  # fmt: skip


def _keluaran(k: Kasus, isi: dict[str, Any]) -> dict[str, Any]:
    s = k.sumber[0]
    return {
        "status": "AI_DRAFT",
        "source_refs": [],
        "cited_spans": [{"source_id": s.source_id, "span": s.teks.splitlines()[0]}],
        "confidence_reason": "alternatif tercatat",
        "unknowns": ["Penerima tugas lengkap belum diketahui."],
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
    argv = ["--fungsi", "P07", "--penyedia", "API_ANTHROPIC"]
    kode = jalankan.main(argv, {"ANTHROPIC_API_KEY": _KUNCI_UJI, "EVAL_ULANG": "1"}, out, err)
    return kode, out.getvalue().splitlines()[-1]


def test_kasus_p07_lolos_format_harness_dan_berjalur_campuran() -> None:
    kasus = _kasus_semua()
    assert len(kasus) >= 3
    assert {k.harapan.jalur for k in kasus} == {"MODEL", "TANPA_MODEL"}
    for k in kasus:
        assert k.sumber[0].source_id.startswith("masalah:")
        assert any(s.source_id.startswith("alternatif:") for s in k.sumber)
        assert any(s.source_id.startswith("otorisasi:") for s in k.sumber)


def test_seluruh_kasus_lulus_dengan_keluaran_ideal_exit_0(monkeypatch) -> None:
    klien = KlienOrakel()
    kode, akhir = _jalan(monkeypatch, klien)
    assert kode == 0, akhir
    assert klien.panggilan == sum(1 for k in _kasus_semua() if k.harapan.jalur == "MODEL")


def test_penilai_menagih_kartu_rujukan_status_change_dan_otorisasi() -> None:
    k = next(k for k in _kasus_semua() if k.harapan.jalur == "MODEL")
    assert nilai(k, "LOLOS", [], _keluaran(k, _isi_ideal(k)), "P07") == []
    isi = _isi_ideal(k)
    isi["decision_card"]["bukti"][0]["source_ids"] = ["bukti:asing"]
    assert "RUJUKAN_TAK_DIKENAL" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P07")
    isi = {**_isi_ideal(k), "required_signoffs": []}
    assert "CHANGE_TIDAK_DISEBUT" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P07")
    isi = {**_isi_ideal(k), "limitation": ["Kartu READY"]}
    assert "STATUS_TERLARANG" in nilai(k, "LOLOS", [], _keluaran(k, isi), "P07")
    isi = {**_isi_ideal(k), "authorization_state": {"change_ditandatangani": True}}
    assert "FIELD_PERSETUJUAN:authorization_state" in nilai(
        k, "LOLOS", [], _keluaran(k, isi), "P07"
    )
    kel = {**_keluaran(k, _isi_ideal(k)), "unknowns": []}
    assert "UNKNOWNS_KOSONG" in nilai(k, "LOLOS", [], kel, "P07")


def test_harness_exit_1_bila_signoff_change_hilang(monkeypatch) -> None:
    klien = KlienOrakel(lambda _k, isi: {**isi, "required_signoffs": []})
    kode, _ = _jalan(monkeypatch, klien)
    assert kode == 1
