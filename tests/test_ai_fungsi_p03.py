"""Tes unit fungsi AI P03 versi terbatas (tag mandat formal): skema, aturan isi, parameter, katalog.

Data sintetis; tanpa basis data dan tanpa jaringan.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from anjab_abk_backend.ai.fungsi_p03 import (
    FIELD_SUMBER_MANDAT_P03,
    FUNGSI_P03,
    KODE_RUJUKAN_TAK_DIKENAL,
    KODE_TANPA_DASAR_MANDAT,
    KODE_UNKNOWNS_KOSONG,
    SKEMA_ISI_P03,
    ParameterP03,
    aturan_p03,
    id_sumber_mandat,
    sumber_mandat_p03,
    uraian_dirujuk_p02,
)
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.katalog import KATALOG_FUNGSI, daftarkan_fungsi
from anjab_abk_backend.ai.keluaran import skema_dengan_amplop
from anjab_abk_backend.ai.penyerap_usulan import ATURAN_ISI
from anjab_abk_backend.config import Settings

_KATA_TERLARANG = {
    "if", "then", "else", "minLength", "maxLength", "minItems", "maxItems", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "pattern",
}  # fmt: skip
_NAMA_TERLARANG = ("approve", "setuju", "skor", "keputusan", "putusan", "assignment")
_US = "usulan:00000000-0000-4000-8000-000000000001"
_M1 = "uraian:ut-1@jbt_a"


@pytest.fixture(autouse=True)
def _bersihkan_registri():
    FUNGSI_TERDAFTAR.clear()
    yield
    FUNGSI_TERDAFTAR.clear()


def _isi(**ubah: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "tag_candidates": [
            {
                "kandidat_ke": 0,
                "jabatan_kode": "GURU-SD",
                "dasar": "MANDAT_FORMAL",
                "status_aktual": "BELUM_DIKETAHUI",
                "source_ids": [_US, _M1],
            }
        ],
        "owner_ambiguities": [
            {"kandidat_ke": 0, "alasan": "jenjang tidak disebut", "jabatan_kode_kandidat": ["A"]}
        ],
    }
    d.update(ubah)
    return d


def _amplop(*ids: str, unknowns: list[str] | None = None) -> dict[str, Any]:
    return {
        "source_refs": [{"source_id": i, "source_hash": "a" * 64} for i in ids],
        "unknowns": ["Sumber penugasan aktual tidak tersedia."] if unknowns is None else unknowns,
    }


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
    return list(Draft202012Validator(SKEMA_ISI_P03).iter_errors(isi))


# --- skema isi ---


def test_skema_isi_sah_json_schema_dan_tanpa_kata_kunci_terlarang():
    Draft202012Validator.check_schema(SKEMA_ISI_P03)
    Draft202012Validator.check_schema(skema_dengan_amplop(SKEMA_ISI_P03))
    assert not (_kunci(SKEMA_ISI_P03) & _KATA_TERLARANG)
    nama = _kunci(SKEMA_ISI_P03["properties"]) - {"type", "items", "properties", "required"}
    for n in nama:
        assert not any(t in n.casefold() for t in _NAMA_TERLARANG), n


def test_keluaran_sah_lolos_skema_dan_aturan_tanpa_pelanggaran():
    assert not _galat(_isi())
    assert aturan_p03(_isi(), _amplop(_US, _M1)) == []


@pytest.mark.parametrize(
    ("field", "nilai"),
    [("status_aktual", "AKTUAL"), ("status_aktual", "DIKETAHUI"), ("dasar", "PENUGASAN_AKTUAL")],
)
def test_skema_menolak_dasar_dan_status_aktual_di_luar_const(field, nilai):
    isi = _isi()
    isi["tag_candidates"][0][field] = nilai
    assert _galat(isi)


def test_skema_menolak_field_tambahan_misalnya_assignment_sources():
    assert _galat(_isi(assignment_sources=[]))
    isi = _isi()
    isi["tag_candidates"][0]["penugasan_id"] = "x"
    assert _galat(isi)


# --- aturan isi ---


def test_tag_tanpa_sumber_uraian_tanpa_dasar_mandat():
    isi = _isi()
    isi["tag_candidates"][0]["source_ids"] = [_US]
    assert aturan_p03(isi, _amplop(_US, _M1)) == [KODE_TANPA_DASAR_MANDAT]
    isi["tag_candidates"][0]["source_ids"] = []
    assert aturan_p03(isi, _amplop(_US, _M1)) == [KODE_TANPA_DASAR_MANDAT]


def test_unknowns_kosong_atau_spasi_unknowns_kosong():
    assert aturan_p03(_isi(), _amplop(_US, _M1, unknowns=[])) == [KODE_UNKNOWNS_KOSONG]
    assert aturan_p03(_isi(), _amplop(_US, _M1, unknowns=["  "])) == [KODE_UNKNOWNS_KOSONG]
    tanpa = {"source_refs": _amplop(_US, _M1)["source_refs"]}
    assert aturan_p03(_isi(), tanpa) == [KODE_UNKNOWNS_KOSONG]


def test_rujukan_asing_rujukan_tak_dikenal_sekali_saja():
    isi = _isi()
    isi["tag_candidates"].append(copy.deepcopy(isi["tag_candidates"][0]))
    for tag in isi["tag_candidates"]:
        tag["source_ids"] = ["uraian:asing@jbt_x"]
    assert aturan_p03(isi, _amplop(_US, _M1)) == [KODE_RUJUKAN_TAK_DIKENAL]


def test_tag_kosong_tetap_menagih_unknowns():
    assert aturan_p03(_isi(tag_candidates=[]), _amplop(_US)) == []
    assert aturan_p03(_isi(tag_candidates=[]), _amplop(_US, unknowns=[])) == [KODE_UNKNOWNS_KOSONG]


def test_aturan_terdaftar_di_atur_isi():
    assert ATURAN_ISI["P03"] is aturan_p03


# --- sumber mandat dan rujukan P02 ---


def test_uraian_dirujuk_p02_hanya_awalan_uraian_unik_urut():
    isi = {
        "task_candidates": [{"source_ids": ["uraian:u1", "dok-1", "uraian:u2"]}],
        "duplicate_suspicions": [{"source_ids": ["uraian:u2", "uraian:u3"]}],
        "split_merge_rationale": [{"source_ids": ["uraian:", 7]}],
        "reviewer_questions": ["uraian:u9"],
    }
    assert uraian_dirujuk_p02(isi) == ["u1", "u2", "u3"]
    assert uraian_dirujuk_p02(None) == []
    assert uraian_dirujuk_p02({"task_candidates": "rusak"}) == []


def test_sumber_mandat_hanya_field_jabatan_dan_tugas():
    nilai = {
        "jabatan_kode": "GURU-SD", "jabatan_nama": "Guru  Kelas", "kode": "G-1", "unit": "SD",
        "tugas_pokok": None, "detil_tugas": "", "uraian": "Menyusun RPP",
        "std_va_type": "VA-Core", "partisipan_nama": "Tidak Boleh", "jabatan_id": "jbt_a",
    }  # fmt: skip
    s = sumber_mandat_p03("ut-1", "jbt_a", nilai)
    assert s.source_id == id_sumber_mandat("ut-1", "jbt_a") == _M1
    assert s.jenis == "KATALOG_TI"
    assert s.teks == (
        "jabatan_kode: GURU-SD\njabatan_nama: Guru Kelas\nkode: G-1\nunit: SD\nuraian: Menyusun RPP"
    )
    assert {b.split(":", 1)[0] for b in s.teks.splitlines()} <= set(FIELD_SUMBER_MANDAT_P03)
    assert s.source_hash == hashlib.sha256(s.teks.encode()).hexdigest()


# --- parameter dan katalog ---


def test_parameter_hanya_kode_tanpa_teks_bebas():
    ParameterP03(jabatan_kode="GURU-SD", periode="2026/27")
    for salah in (
        {"jabatan_kode": "GURU SD", "periode": "2026/27"},
        {"jabatan_kode": "G", "periode": "2026/27 ganjil"},
        {"jabatan_kode": "G", "periode": "2026/27", "catatan": "bebas"},
    ):
        with pytest.raises(ValidationError):
            ParameterP03(**salah)


def test_katalog_memuat_p03_tetapi_bawaan_tidak_aktif():
    assert KATALOG_FUNGSI["P03"] is FUNGSI_P03
    bawaan = Settings(_env_file=None)
    assert bawaan.ai_fungsi_aktif == []
    daftarkan_fungsi(bawaan)
    assert "P03" not in FUNGSI_TERDAFTAR
    daftarkan_fungsi(Settings(_env_file=None, ai_fungsi_aktif=["P03"]))
    assert FUNGSI_TERDAFTAR == {"P03": FUNGSI_P03}
