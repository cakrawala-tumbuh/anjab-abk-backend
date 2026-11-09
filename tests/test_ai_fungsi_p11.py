"""Tes unit fungsi AI P11 (pengusul konteks): skema, aturan isi, parameter, katalog, sumber.

Data sintetis; tanpa basis data dan tanpa jaringan.
"""

from __future__ import annotations

from typing import Any, get_args

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from anjab_abk_backend.ai.fungsi_p11 import (
    FUNGSI_P11,
    KODE_KANDIDAT_BERLEBIH,
    KODE_KONTEKS_TAK_DIKENAL,
    KODE_RUJUKAN_TAK_DIKENAL,
    KODE_TEMA_TERLALU_PANJANG,
    SASARAN_KATALOG_KONTEKS,
    SKEMA_ISI_P11,
    ParameterP11,
    aturan_p11,
)
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.katalog import KATALOG_FUNGSI, daftarkan_fungsi
from anjab_abk_backend.ai.keluaran import skema_dengan_amplop
from anjab_abk_backend.ai.penyerap_usulan import ATURAN_ISI
from anjab_abk_backend.ai.sumber_konteks import (
    FIELD_SUMBER_KONTEKS,
    sumber_konteks,
    teks_sumber_konteks,
)
from anjab_abk_backend.config import Settings
from anjab_abk_backend.redesain.schemas.kosakata import Gelombang
from anjab_abk_backend.schemas.ai_usulan import SasaranUsulan

_KATA_TERLARANG = {
    "if", "then", "else", "minLength", "maxLength", "maxItems", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "pattern",
}  # fmt: skip
_NAMA_TERLARANG = ("approve", "setuju", "skor", "keputusan", "putusan", "verified", "nama")
_K1 = "konteks:k-1"
_K2 = "konteks:k-2"
_M1 = "masalah:m-1"


@pytest.fixture(autouse=True)
def _bersihkan_registri():
    FUNGSI_TERDAFTAR.clear()
    yield
    FUNGSI_TERDAFTAR.clear()


def _kandidat(**ubah: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "tema": "Penyamaan format nilai rapor",
        "ruang_dugaan": "Wali kelas menyamakan format nilai dari beberapa guru mata pelajaran.",
        "sumber_draft": "Konteks K-01 dan masalah M-K01-01.",
        "batas_pemeriksaan": "Belum diukur berapa jam yang terpakai per semester.",
        "gelombang_saran": "G1",
        "mirip_kode": "K-01",
        "source_ids": [_K1, _M1],
    }
    d.update(ubah)
    return d


def _isi(*kandidat: dict[str, Any]) -> dict[str, Any]:
    return {
        "konteks_candidates": list(kandidat) or [_kandidat()],
        "reviewer_questions": ["Apakah format nilai ditetapkan yayasan?"],
    }


def _amplop(jumlah: int = 3, kode: tuple[str, ...] = ("K-01", "K-02")) -> dict[str, Any]:
    return {
        "source_refs": [{"source_id": i, "source_hash": "a" * 64} for i in (_K1, _K2, _M1)],
        "konteks_server": {"jumlah_kandidat": jumlah, "kode_konteks_ada": list(kode)},
    }


def _galat(isi: dict[str, Any]) -> list:
    return list(Draft202012Validator(SKEMA_ISI_P11).iter_errors(isi))


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


def test_skema_sah_tanpa_angka_dan_minitems_hanya_kandidat():
    Draft202012Validator.check_schema(SKEMA_ISI_P11)
    Draft202012Validator.check_schema(skema_dengan_amplop(SKEMA_ISI_P11))
    simpul = _simpul(SKEMA_ISI_P11)
    for jalur, n in simpul:
        assert not (_KATA_TERLARANG & set(n)), jalur
        if n.get("type") == "object":
            assert n["additionalProperties"] is False, jalur
            assert set(n["required"]) == set(n["properties"]), jalur
    assert [j for j, n in simpul if n.get("type") in ("number", "integer")] == []
    minitems = [(j, n["minItems"]) for j, n in simpul if "minItems" in n]
    assert minitems == [("/properties/konteks_candidates", 1)]
    nama = {k for _, n in simpul for k in (n.get("properties") or {})}
    for n in nama:
        assert not any(t in n.casefold() for t in _NAMA_TERLARANG), n


def test_skema_gelombang_dikunci_ke_nilai_gelombang_dan_mirip_kode_boleh_null():
    item = SKEMA_ISI_P11["properties"]["konteks_candidates"]["items"]["properties"]
    assert item["gelombang_saran"]["enum"] == list(get_args(Gelombang))
    assert _galat(_isi(_kandidat(mirip_kode=None))) == []
    assert _galat(_isi(_kandidat(gelombang_saran="G9")))
    assert _galat({"konteks_candidates": [], "reviewer_questions": []})
    assert _galat({**_isi(), "status": "APPROVE"})


def test_keluaran_sah_lolos_skema_dan_aturan_isi():
    isi = _isi(_kandidat(), _kandidat(mirip_kode=None, source_ids=[_K2], gelombang_saran="G2"))
    assert _galat(isi) == []
    assert aturan_p11(isi, _amplop()) == []


# --- aturan isi ---


def test_rujukan_asing_atau_kosong_rujukan_tak_dikenal():
    assert aturan_p11(_isi(_kandidat(source_ids=["konteks:asing"])), _amplop()) == [
        KODE_RUJUKAN_TAK_DIKENAL
    ]
    assert aturan_p11(_isi(_kandidat(source_ids=[])), _amplop()) == [KODE_RUJUKAN_TAK_DIKENAL]


def test_mirip_kode_tak_dikenal():
    assert aturan_p11(_isi(_kandidat(mirip_kode="K-99")), _amplop()) == [KODE_KONTEKS_TAK_DIKENAL]


def test_empat_kandidat_dengan_jumlah_tiga_kandidat_berlebih():
    isi = _isi(*[_kandidat() for _ in range(4)])
    assert _galat(isi) == []
    assert aturan_p11(isi, _amplop(jumlah=3)) == [KODE_KANDIDAT_BERLEBIH]
    assert aturan_p11(isi, _amplop(jumlah=4)) == []


def test_tanpa_konteks_server_batas_lima_dan_mirip_kode_harus_null():
    amplop = {"source_refs": [{"source_id": _K1}, {"source_id": _M1}]}
    assert aturan_p11(_isi(*[_kandidat(mirip_kode=None) for _ in range(5)]), amplop) == []
    six = _isi(*[_kandidat(mirip_kode=None) for _ in range(6)])
    assert aturan_p11(six, amplop) == [KODE_KANDIDAT_BERLEBIH]
    assert aturan_p11(_isi(_kandidat()), amplop) == [KODE_KONTEKS_TAK_DIKENAL]


def test_tema_lebih_dari_200_karakter():
    assert aturan_p11(_isi(_kandidat(tema="x" * 200)), _amplop()) == []
    assert aturan_p11(_isi(_kandidat(tema="x" * 201)), _amplop()) == [KODE_TEMA_TERLALU_PANJANG]


def test_kode_paling_banyak_sekali_dan_urut():
    buruk = _kandidat(source_ids=["x:1"], mirip_kode="K-99", tema="t" * 201)
    isi = _isi(buruk, buruk)
    assert aturan_p11(isi, _amplop(jumlah=1)) == [
        KODE_RUJUKAN_TAK_DIKENAL,
        KODE_KONTEKS_TAK_DIKENAL,
        KODE_KANDIDAT_BERLEBIH,
        KODE_TEMA_TERLALU_PANJANG,
    ]


# --- parameter, katalog, saklar ---


def test_parameter_tanpa_teks_bebas():
    p = ParameterP11(jumlah_kandidat=3, sertakan_masalah=True, kode_konteks_ada=["K-01"])
    assert p.model_dump() == {
        "jumlah_kandidat": 3,
        "sertakan_masalah": True,
        "kode_konteks_ada": ["K-01"],
    }
    for salah in (
        {"jumlah_kandidat": 0, "sertakan_masalah": True},
        {"jumlah_kandidat": 6, "sertakan_masalah": True},
        {"jumlah_kandidat": 1, "sertakan_masalah": True, "kode_konteks_ada": ["ada spasi"]},
        {"jumlah_kandidat": 1, "sertakan_masalah": True, "catatan": "bebas"},
    ):
        with pytest.raises(ValidationError):
            ParameterP11(**salah)


def test_katalog_memuat_p11_dan_saklar_bawaan_tidak_berubah():
    assert KATALOG_FUNGSI["P11"] is FUNGSI_P11
    assert ATURAN_ISI["P11"] is aturan_p11
    assert SASARAN_KATALOG_KONTEKS == "KATALOG"
    assert SasaranUsulan.REDESAIN_KONTEKS.value == "REDESAIN_KONTEKS"
    cfg = Settings(_env_file=None)
    assert cfg.ai_fungsi_aktif == []
    assert cfg.ai_jenis_sumber_diizinkan == ["SINTETIS"]
    daftarkan_fungsi(cfg)
    assert "P11" not in FUNGSI_TERDAFTAR
    daftarkan_fungsi(Settings(_env_file=None, ai_fungsi_aktif=["P11"]))
    assert FUNGSI_TERDAFTAR["P11"] is FUNGSI_P11


def test_instruksi_menegaskan_ruang_dugaan_dan_mirip_kode():
    teks = FUNGSI_P11.instruksi
    for frasa in ("ruang dugaan, BUKAN temuan", "batas_pemeriksaan", "sumber_draft",
                  "nama orang", "mirip_kode", "kode_konteks_ada"):  # fmt: skip
        assert frasa in teks, frasa


# --- sumber konteks (murni) ---


def test_teks_masalah_tanpa_sekolah_dan_kode_orang():
    nilai = {
        "kode": "M-K01-01", "konteks_kode": "K-01", "rumusan_hipotesis": "Rekap  nilai berulang",
        "sumber_awal_keterbatasan": "Satu diskusi", "status_awal": "Hipotesis",
        "periode_acuan": "2026/27", "penjelasan_alternatif": None,
        "sekolah_id": "sek-rahasia-11", "keterangan_sekolah": "SD Fiktif Rahasia",
        "pic_kode_orang": "ORG-7731",
    }  # fmt: skip
    s = sumber_konteks("masalah", "m-1", nilai)
    assert s.source_id == "masalah:m-1" and s.jenis == "REDESAIN"
    for rahasia in ("sek-rahasia-11", "SD Fiktif Rahasia", "ORG-7731"):
        assert rahasia not in s.teks
    assert s.teks == (
        "kode: M-K01-01\nkonteks_kode: K-01\nrumusan_hipotesis: Rekap nilai berulang\n"
        "sumber_awal_keterbatasan: Satu diskusi\nstatus_awal: Hipotesis\nperiode_acuan: 2026/27"
    )
    for terlarang in ("sekolah_id", "keterangan_sekolah", "pic_kode_orang"):
        assert terlarang not in FIELD_SUMBER_KONTEKS["masalah"]


def test_teks_konteks_field_tetap():
    assert FIELD_SUMBER_KONTEKS["konteks"] == (
        "kode", "tema", "gelombang", "ruang_dugaan", "sumber_draft", "batas_pemeriksaan"
    )  # fmt: skip
    teks = teks_sumber_konteks("konteks", {"kode": "K-01", "tema": "Rapor", "aktif": True})
    assert teks == "kode: K-01\ntema: Rapor"
