"""Tes unit fungsi AI P08 (sintesis bukti riset): skema, aturan isi, parameter, katalog, sumber.

Data sintetis; tanpa basis data dan tanpa jaringan.
"""

from __future__ import annotations

from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from anjab_abk_backend.ai.fungsi_p08 import (
    FUNGSI_P08,
    KODE_HASIL_TANPA_STATISTIK,
    KODE_KLAIM_TANPA_STATISTIK,
    KODE_KLAIM_TERLARANG,
    KODE_RUJUKAN_TAK_DIKENAL,
    SKEMA_ISI_P08,
    ParameterP08,
    aturan_p08,
)
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.katalog import KATALOG_FUNGSI, daftarkan_fungsi
from anjab_abk_backend.ai.keluaran import skema_dengan_amplop
from anjab_abk_backend.ai.penyerap_usulan import ATURAN_ISI
from anjab_abk_backend.ai.sumber_riset import (
    AWALAN_SUMBER_RISET,
    FIELD_SUMBER_RISET,
    sumber_riset,
)
from anjab_abk_backend.config import Settings

_KATA_TERLARANG = {
    "if", "then", "else", "minLength", "maxLength", "maxItems", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "pattern",
}  # fmt: skip
_NAMA_TERLARANG = ("approve", "setuju", "skor", "keputusan", "putusan", "verified", "signif")
_P = "protokol:p-1"
_S = "statistik:s-1"
_K = "kasus-negatif:k-1"
_V = "versi-metode:v-1"


@pytest.fixture(autouse=True)
def _bersihkan_registri():
    FUNGSI_TERDAFTAR.clear()
    yield
    FUNGSI_TERDAFTAR.clear()


def _isi(**ubah: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "manuscript_sections": [
            {"bagian": "METODE",
             "teks": "Reliabilitas dihitung dengan Cronbach alpha per sub-skala",
             "source_ids": [_P, _V]},
            {"bagian": "HASIL", "teks": "Alpha sub-skala Tuntutan 0,81; satu sekolah di bawah 0,6",
             "source_ids": [_S, _K]},
        ],
        "evidence_table": [
            {"klaim": "Sub-skala Tuntutan reliabel pada sampel ini", "statistik_ids": [_S],
             "batasan": "Hanya 34 responden"},
        ],
        "limitations": ["Sampel sintetis satu periode"],
        "unsupported_claims": [
            {"klaim": "Instrumen layak terbit di jurnal Q1",
             "alasan": "Tidak ada keluaran analisis"},
        ],
    }  # fmt: skip
    d.update(ubah)
    return d


def _amplop(*ids: str) -> dict[str, Any]:
    return {"source_refs": [{"source_id": i, "source_hash": "a" * 64} for i in ids]}


_SEMUA = _amplop(_P, _S, _K, _V)


def _galat(isi: dict[str, Any]) -> list:
    return list(Draft202012Validator(SKEMA_ISI_P08).iter_errors(isi))


def _simpul(obj: Any, jalur: str = "") -> list[tuple[str, dict]]:
    if isinstance(obj, dict):
        hasil = [(jalur, obj)]
        for k, v in obj.items():
            hasil += _simpul(v, f"{jalur}/{k}")
        return hasil
    if isinstance(obj, list):
        return [x for i, v in enumerate(obj) for x in _simpul(v, f"{jalur}/{i}")]
    return []


# --- skema isi ---


def test_skema_sah_tanpa_angka_dan_minitems_hanya_limitations():
    Draft202012Validator.check_schema(SKEMA_ISI_P08)
    Draft202012Validator.check_schema(skema_dengan_amplop(SKEMA_ISI_P08))
    simpul = _simpul(SKEMA_ISI_P08)
    for jalur, n in simpul:
        assert not (_KATA_TERLARANG & set(n)), jalur
        if n.get("type") == "object":
            assert n["additionalProperties"] is False, jalur
            assert set(n["required"]) == set(n["properties"]), jalur
    assert [j for j, n in simpul if n.get("type") in ("number", "integer")] == []
    minitems = [(j, n["minItems"]) for j, n in simpul if "minItems" in n]
    assert minitems == [("/properties/limitations", 1)]
    nama = {k for _, n in simpul for k in (n.get("properties") or {})}
    for n in nama:
        assert not any(t in n.casefold() for t in _NAMA_TERLARANG), n


def test_keluaran_sah_lolos_skema_dan_aturan_isi():
    isi = _isi()
    assert _galat(isi) == []
    assert aturan_p08(isi, _SEMUA) == []


def test_limitations_kosong_ditolak_skema():
    assert _galat(_isi(limitations=[]))


def test_bagian_asing_dan_field_tambahan_ditolak_skema():
    isi = _isi()
    isi["manuscript_sections"][0]["bagian"] = "DISKUSI"
    assert _galat(isi)
    assert _galat(_isi(p_value=0.01))
    isi = _isi()
    isi["evidence_table"][0]["status"] = "VERIFIED"
    assert _galat(isi)


# --- aturan isi ---


def test_hasil_hanya_merujuk_protokol_hasil_tanpa_statistik():
    isi = _isi()
    isi["manuscript_sections"][1]["source_ids"] = [_P]
    assert aturan_p08(isi, _SEMUA) == [KODE_HASIL_TANPA_STATISTIK]


def test_jurnal_q1_klaim_terlarang():
    isi = _isi()
    isi["manuscript_sections"][0]["teks"] = "Metode mengikuti standar jurnal Q1"
    assert aturan_p08(isi, _SEMUA) == [KODE_KLAIM_TERLARANG]
    isi = _isi()
    isi["evidence_table"][0]["klaim"] = "Layak Q1"
    assert aturan_p08(isi, _SEMUA) == [KODE_KLAIM_TERLARANG]


def test_q1_harus_kata_utuh_dan_unsupported_claims_tidak_diperiksa():
    isi = _isi()
    isi["manuscript_sections"][0]["teks"] = "Kuartil Q12 dan kode XQ1 bukan peringkat"
    assert aturan_p08(isi, _SEMUA) == []
    assert "Q1" in _isi()["unsupported_claims"][0]["klaim"]


def test_signifikan_tanpa_sumber_statistik_klaim_terlarang():
    isi = _isi()
    isi["manuscript_sections"][0]["teks"] = "Perbedaan ini SIGNIFIKAN secara praktis"
    assert aturan_p08(isi, _SEMUA) == [KODE_KLAIM_TERLARANG]
    isi = _isi()
    isi["manuscript_sections"][0]["teks"] = "Metode baru non-inferior dibanding lama"
    assert aturan_p08(isi, _SEMUA) == [KODE_KLAIM_TERLARANG]


def test_signifikan_boleh_di_bagian_yang_merujuk_statistik():
    isi = _isi()
    isi["manuscript_sections"][1]["teks"] = "Keluaran statistik mencatat selisih signifikan"
    assert aturan_p08(isi, _SEMUA) == []


def test_statistik_ids_berawalan_protokol_klaim_tanpa_statistik():
    isi = _isi()
    isi["evidence_table"][0]["statistik_ids"] = [_P]
    assert aturan_p08(isi, _SEMUA) == [KODE_KLAIM_TANPA_STATISTIK]
    isi = _isi()
    isi["evidence_table"][0]["statistik_ids"] = []
    assert aturan_p08(isi, _SEMUA) == [KODE_KLAIM_TANPA_STATISTIK]


def test_rujukan_asing_atau_source_ids_kosong_rujukan_tak_dikenal():
    isi = _isi()
    isi["evidence_table"][0]["statistik_ids"] = ["statistik:asing"]
    assert aturan_p08(isi, _SEMUA) == [KODE_RUJUKAN_TAK_DIKENAL]
    isi = _isi()
    isi["manuscript_sections"][0]["source_ids"] = []
    assert aturan_p08(isi, _SEMUA) == [KODE_RUJUKAN_TAK_DIKENAL]


def test_kode_paling_banyak_sekali_dan_urut():
    isi = _isi()
    isi["manuscript_sections"][0]["source_ids"] = ["x:1"]
    isi["manuscript_sections"][1] = {"bagian": "HASIL", "teks": "Jurnal Q1", "source_ids": [_P]}
    isi["evidence_table"] = [{"klaim": "a", "statistik_ids": [_K], "batasan": "b"}] * 2
    assert aturan_p08(isi, _SEMUA) == [
        KODE_RUJUKAN_TAK_DIKENAL,
        KODE_KLAIM_TANPA_STATISTIK,
        KODE_HASIL_TANPA_STATISTIK,
        KODE_KLAIM_TERLARANG,
    ]


# --- parameter, katalog, saklar ---


def test_parameter_hanya_kode_versi_periode():
    p = ParameterP08(protokol_kode="P08-DCS", protokol_versi=2, periode="2026/27")
    assert p.model_dump() == {"protokol_kode": "P08-DCS", "protokol_versi": 2, "periode": "2026/27"}
    for salah in (
        {"protokol_kode": "ada spasi", "protokol_versi": 1, "periode": "2026/27"},
        {"protokol_kode": "P", "protokol_versi": 0, "periode": "2026/27"},
        {"protokol_kode": "P", "protokol_versi": 1, "periode": "x y"},
        {"protokol_kode": "P", "protokol_versi": 1, "periode": "2026/27", "catatan": "bebas"},
    ):
        with pytest.raises(ValidationError):
            ParameterP08(**salah)


def test_katalog_memuat_p08_dan_saklar_bawaan_tidak_berubah():
    assert KATALOG_FUNGSI["P08"] is FUNGSI_P08
    assert ATURAN_ISI["P08"] is aturan_p08
    cfg = Settings(_env_file=None)
    assert cfg.ai_fungsi_aktif == []
    assert cfg.ai_jenis_sumber_diizinkan == ["SINTETIS"]
    daftarkan_fungsi(cfg)
    assert "P08" not in FUNGSI_TERDAFTAR
    daftarkan_fungsi(Settings(_env_file=None, ai_fungsi_aktif=["P08"]))
    assert FUNGSI_TERDAFTAR["P08"] is FUNGSI_P08


def test_instruksi_melarang_karangan_dan_menuntut_kasus_negatif():
    teks = FUNGSI_P08.instruksi
    for frasa in ("mengarang", "Q1", "signifikan", "non-inferior", "kasus-negatif:",
                  "unsupported_claims", "statistik:"):  # fmt: skip
        assert frasa in teks, frasa


# --- sumber riset (murni) ---


def test_sumber_riset_hanya_field_yang_diizinkan_dan_blok_apa_adanya():
    s = sumber_riset(
        "statistik",
        "s-1",
        {"nama_analisis": "Alpha  DCS", "kode_sumber_ref": "a.py@1",
         "keluaran": "n  alpha\n34 0.81", "status": "DRAF", "dibuat_oleh": "orang-1",
         "diverifikasi_oleh": "orang-2"},
    )  # fmt: skip
    assert s.source_id == "statistik:s-1" and s.jenis == "RISET"
    assert s.teks == (
        "nama_analisis: Alpha DCS\nkode_sumber_ref: a.py@1\nkeluaran:\nn  alpha\n34 0.81"
    )
    assert AWALAN_SUMBER_RISET == ("protokol:", "statistik:", "kasus-negatif:", "versi-metode:")
    assert "pemeriksa_pemutus" not in FIELD_SUMBER_RISET["versi-metode"]
    assert FIELD_SUMBER_RISET["protokol"] == ("kode", "versi", "isi_hash", "isi")
