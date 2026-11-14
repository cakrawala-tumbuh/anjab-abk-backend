"""Tes unit fungsi AI P05 (hipotesis proses): skema, aturan isi, parameter, katalog.

Data sintetis; tanpa basis data dan tanpa jaringan.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from anjab_abk_backend.ai.fungsi_p05 import (
    FUNGSI_P05,
    KODE_HIPOTESIS_TANPA_PENYANGKAL,
    KODE_RUJUKAN_TAK_DIKENAL,
    SKEMA_ISI_P05,
    ParameterP05,
    aturan_p05,
)
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.katalog import KATALOG_FUNGSI, daftarkan_fungsi
from anjab_abk_backend.ai.keluaran import skema_dengan_amplop
from anjab_abk_backend.ai.penyerap_usulan import ATURAN_ISI
from anjab_abk_backend.ai.sumber_redesain import (
    FIELD_SUMBER_REDESAIN,
    JENIS_SUMBER_REDESAIN,
    sumber_redesain,
)
from anjab_abk_backend.config import Settings

_KATA_TERLARANG = {
    "if", "then", "else", "minLength", "maxLength", "minItems", "maxItems", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "pattern",
}  # fmt: skip
_NAMA_TERLARANG = ("approve", "setuju", "skor", "keputusan", "putusan")
_L1 = "langkah:l-1"
_B1 = "bukti:b-1"


@pytest.fixture(autouse=True)
def _bersihkan_registri():
    FUNGSI_TERDAFTAR.clear()
    yield
    FUNGSI_TERDAFTAR.clear()


def _isi(**ubah: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "process_draft": {
            "langkah": [
                {"urutan": 1, "uraian": "Guru mengisi nilai", "pelaksana": "Guru",
                 "source_ids": [_L1]},
            ]
        },
        "issue_hypotheses": [
            {"hipotesis": "Format lembar nilai berbeda", "status": "HIPOTESIS",
             "source_ids": [_L1, _B1]},
        ],
        "disconfirming_checks": [
            {"hipotesis_ke": 0, "pemeriksaan": "Bandingkan waktu rekap dengan format seragam",
             "data_dibutuhkan": "Waktu penyerahan rekap dua semester"},
        ],
        "evidence_gaps": ["Lama penyalinan nilai belum diukur"],
    }  # fmt: skip
    d.update(ubah)
    return d


def _amplop(*ids: str) -> dict[str, Any]:
    return {"source_refs": [{"source_id": i, "source_hash": "a" * 64} for i in ids]}


def _kunci(obj: Any) -> set[str]:
    if isinstance(obj, dict):
        hasil = set(obj)
        for v in obj.values():
            hasil |= _kunci(v)
        return hasil
    if isinstance(obj, list):
        return set().union(*(_kunci(x) for x in obj)) if obj else set()
    return set()


def _galat(isi: dict[str, Any]) -> list:
    return list(Draft202012Validator(SKEMA_ISI_P05).iter_errors(isi))


# --- skema isi ---


def test_skema_isi_sah_json_schema_dan_tanpa_kata_kunci_terlarang():
    Draft202012Validator.check_schema(SKEMA_ISI_P05)
    Draft202012Validator.check_schema(skema_dengan_amplop(SKEMA_ISI_P05))
    assert not (_kunci(SKEMA_ISI_P05) & _KATA_TERLARANG)
    nama = _kunci(SKEMA_ISI_P05["properties"]) - {"type", "items", "properties", "required"}
    for n in nama:
        assert not any(t in n.casefold() for t in _NAMA_TERLARANG), n


def test_keluaran_sah_lolos_skema_dan_aturan_isi():
    isi = _isi()
    assert _galat(isi) == []
    assert aturan_p05(isi, _amplop(_L1, _B1)) == []


def test_status_selain_hipotesis_ditolak_skema():
    isi = _isi()
    isi["issue_hypotheses"][0]["status"] = "TERBUKTI"
    assert _galat(isi)


def test_field_tambahan_ditolak_skema():
    assert _galat(_isi(skor=5))
    isi = _isi()
    isi["issue_hypotheses"][0]["akar_penyebab"] = True
    assert _galat(isi)


# --- aturan isi ---


def test_hipotesis_tanpa_penyangkal():
    isi = _isi(disconfirming_checks=[])
    assert aturan_p05(isi, _amplop(_L1, _B1)) == [KODE_HIPOTESIS_TANPA_PENYANGKAL]
    isi = _isi()
    isi["disconfirming_checks"][0]["hipotesis_ke"] = 1
    assert aturan_p05(isi, _amplop(_L1, _B1)) == [KODE_HIPOTESIS_TANPA_PENYANGKAL]


def test_source_ids_asing_atau_kosong_rujukan_tak_dikenal():
    isi = _isi()
    isi["issue_hypotheses"][0]["source_ids"] = ["bukti:asing"]
    assert aturan_p05(isi, _amplop(_L1, _B1)) == [KODE_RUJUKAN_TAK_DIKENAL]
    isi = _isi()
    isi["process_draft"]["langkah"][0]["source_ids"] = []
    assert aturan_p05(isi, _amplop(_L1, _B1)) == [KODE_RUJUKAN_TAK_DIKENAL]
    assert aturan_p05(_isi(), _amplop(_L1)) == [KODE_RUJUKAN_TAK_DIKENAL]


def test_kode_paling_banyak_sekali_dan_gabungan():
    isi = _isi(disconfirming_checks=[])
    isi["issue_hypotheses"].append(copy.deepcopy(isi["issue_hypotheses"][0]))
    for h in isi["issue_hypotheses"]:
        h["source_ids"] = ["x:1"]
    assert aturan_p05(isi, _amplop(_L1)) == [
        KODE_RUJUKAN_TAK_DIKENAL,
        KODE_HIPOTESIS_TANPA_PENYANGKAL,
    ]


def test_tanpa_hipotesis_tidak_ditagih_penyangkal():
    isi = _isi(issue_hypotheses=[], disconfirming_checks=[])
    assert aturan_p05(isi, _amplop(_L1)) == []


# --- parameter, katalog, saklar ---


def test_parameter_hanya_kode_tanpa_teks_bebas():
    p = ParameterP05(masalah_id="3f2b8c1e-5d4a-4e6f-9a7b-1c2d3e4f5a6b", periode="2026/27")
    assert p.model_dump() == {
        "masalah_id": "3f2b8c1e-5d4a-4e6f-9a7b-1c2d3e4f5a6b",
        "periode": "2026/27",
    }
    with pytest.raises(ValidationError):
        ParameterP05(masalah_id="m 1", periode="2026/27")
    with pytest.raises(ValidationError):
        ParameterP05(masalah_id="m1", periode="2026/27", catatan="bebas")


def test_instruksi_p05_aturan_status_ai_draft_dan_batas_evidence_gap():
    teks = " ".join(FUNGSI_P05.instruksi.split())
    aturan = teks.split("8. Aturan status.", 1)[1]
    assert "AI_DRAFT" in aturan and "EVIDENCE_GAP" in aturan and "evidence_gaps" in aturan
    assert "tidak ada satu pun span" in aturan
    assert "Setiap hipotesis berstatus HIPOTESIS" in teks
    assert FUNGSI_P05.prompt_version == "p05-2"


def test_katalog_memuat_p05_dan_saklar_bawaan_tidak_berubah():
    assert KATALOG_FUNGSI["P05"] is FUNGSI_P05
    assert ATURAN_ISI["P05"] is aturan_p05
    cfg = Settings(_env_file=None)
    assert cfg.ai_fungsi_aktif == []
    assert cfg.ai_jenis_sumber_diizinkan == ["SINTETIS"]
    daftarkan_fungsi(cfg)
    assert "P05" not in FUNGSI_TERDAFTAR
    daftarkan_fungsi(Settings(_env_file=None, ai_fungsi_aktif=["P05"]))
    assert FUNGSI_TERDAFTAR["P05"] is FUNGSI_P05


# --- perakit sumber (murni) ---


def test_sumber_redesain_berjenis_redesain_dan_membuang_kunci_asing():
    s = sumber_redesain(
        "konfirmasi",
        "f-1",
        {"kode_orang": "O-0001", "cerita_sebelum": "rahasia", "catatan_akses": "x", "k1": "Ya"},
    )
    assert s.source_id == "konfirmasi:f-1" and s.jenis == JENIS_SUMBER_REDESAIN == "REDESAIN"
    assert "cerita_sebelum" not in s.teks and "rahasia" not in s.teks
    assert "catatan_akses" not in s.teks
    assert s.teks == "kode_orang: O-0001\nk1: Ya"
    assert "cerita_sebelum" not in FIELD_SUMBER_REDESAIN["konfirmasi"]
    assert "catatan_privasi_gap" not in FIELD_SUMBER_REDESAIN["bukti"]
