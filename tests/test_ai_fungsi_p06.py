"""Tes unit fungsi AI P06 (draf opsi): skema, aturan isi, parameter, katalog, sumber alternatif.

Data sintetis; tanpa basis data dan tanpa jaringan.
"""

from __future__ import annotations

from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from anjab_abk_backend.ai.fungsi_p06 import (
    FUNGSI_P06,
    KODE_ANGKA_FTE,
    KODE_RUJUKAN_TAK_DIKENAL,
    KODE_STATUS_TERLARANG,
    OPSI_APLIKASI_P06,
    SKEMA_ISI_P06,
    ParameterP06,
    aturan_p06,
)
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.katalog import KATALOG_FUNGSI, daftarkan_fungsi
from anjab_abk_backend.ai.keluaran import skema_dengan_amplop
from anjab_abk_backend.ai.penyerap_usulan import ATURAN_ISI
from anjab_abk_backend.ai.sumber_redesain import (
    AWALAN_SUMBER_REDESAIN,
    FIELD_SUMBER_REDESAIN,
    sumber_redesain,
)
from anjab_abk_backend.ai.syarat_f4 import VERSI_SYARAT_F4
from anjab_abk_backend.config import Settings

_KATA_TERLARANG = {
    "if", "then", "else", "minLength", "maxLength", "maxItems", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "pattern",
}  # fmt: skip
_NAMA_TERLARANG = ("approve", "setuju", "skor", "keputusan", "putusan", "fte", "verified")
_M = "masalah:m-1"
_A = "alternatif:a-1"


@pytest.fixture(autouse=True)
def _bersihkan_registri():
    FUNGSI_TERDAFTAR.clear()
    yield
    FUNGSI_TERDAFTAR.clear()


def _isi(**ubah: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "options": [
            {"jenis": "STATUS_QUO", "opsi_aplikasi": "Pertahankan",
             "uraian": "Alur rekap tetap seperti sekarang",
             "fakta_sumber": [{"pernyataan": "Ada tiga format lembar nilai", "source_ids": [_M]}],
             "asumsi": []},
            {"jenis": "SIMPLIFY", "opsi_aplikasi": "Sederhanakan",
             "uraian": "Satu format lembar nilai untuk semua guru",
             "fakta_sumber": [{"pernyataan": "Format berbeda antar guru", "source_ids": [_M, _A]}],
             "asumsi": ["Guru bersedia memakai format baru"]},
            {"jenis": "TRANSFER", "opsi_aplikasi": None, "uraian": "Belum ada penerima jelas",
             "fakta_sumber": [], "asumsi": []},
        ],
        "scenario_assumptions": ["Jumlah guru per kelas tidak berubah"],
        "unknown_parameters": [
            {"parameter": "Lama penyalinan per kelas", "alasan": "Belum diukur"},
        ],
        "risks": [{"risiko": "Lembar lama masih beredar", "opsi_ke": 1}],
        "checks": [{"pemeriksaan": "Uji format pada satu kelas", "opsi_ke": 1}],
    }  # fmt: skip
    d.update(ubah)
    return d


def _amplop(*ids: str) -> dict[str, Any]:
    return {"source_refs": [{"source_id": i, "source_hash": "a" * 64} for i in ids]}


def _galat(isi: dict[str, Any]) -> list:
    return list(Draft202012Validator(SKEMA_ISI_P06).iter_errors(isi))


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


def test_skema_sah_tanpa_angka_selain_opsi_ke_dan_minitems_hanya_unknown_parameters():
    Draft202012Validator.check_schema(SKEMA_ISI_P06)
    Draft202012Validator.check_schema(skema_dengan_amplop(SKEMA_ISI_P06))
    simpul = _simpul(SKEMA_ISI_P06)
    for jalur, n in simpul:
        assert not (_KATA_TERLARANG & set(n)), jalur
        if n.get("type") == "object":
            assert n["additionalProperties"] is False, jalur
            assert set(n["required"]) == set(n["properties"]), jalur
    angka = [j for j, n in simpul if n.get("type") in ("number", "integer")]
    assert angka == [
        "/properties/risks/items/properties/opsi_ke",
        "/properties/checks/items/properties/opsi_ke",
    ]
    minitems = [(j, n["minItems"]) for j, n in simpul if "minItems" in n]
    assert minitems == [("/properties/unknown_parameters", 1)]
    nama = {k for _, n in simpul for k in (n.get("properties") or {})}
    for n in nama:
        assert not any(t in n.casefold() for t in _NAMA_TERLARANG), n


def test_keluaran_sah_lolos_skema_dan_aturan_isi():
    isi = _isi()
    assert _galat(isi) == []
    assert aturan_p06(isi, _amplop(_M, _A)) == []


def test_unknown_parameters_kosong_ditolak_skema():
    assert _galat(_isi(unknown_parameters=[]))


def test_jenis_asing_ditolak_skema():
    isi = _isi()
    isi["options"][0]["jenis"] = "OUTSOURCE"
    assert _galat(isi)


def test_opsi_aplikasi_hanya_tujuh_opsi_alternatif_atau_null():
    assert len(OPSI_APLIKASI_P06) == 7 and "Alihkan tugas bersyarat" in OPSI_APLIKASI_P06
    isi = _isi()
    isi["options"][0]["opsi_aplikasi"] = "Tambah formasi"
    assert _galat(isi)


def test_field_tambahan_ditolak_skema():
    assert _galat(_isi(fte=1))
    isi = _isi()
    isi["options"][0]["status"] = "READY"
    assert _galat(isi)


# --- aturan isi ---


def test_ready_pada_isi_status_terlarang():
    isi = _isi()
    isi["options"][1]["uraian"] = "Opsi ini ready untuk dijalankan"
    assert aturan_p06(isi, _amplop(_M, _A)) == [KODE_STATUS_TERLARANG]
    isi = _isi(scenario_assumptions=["Status VERIFIED oleh tim"])
    assert aturan_p06(isi, _amplop(_M, _A)) == [KODE_STATUS_TERLARANG]
    isi = _isi(checks=[{"pemeriksaan": "Minta approve kepala sekolah", "opsi_ke": 0}])
    assert aturan_p06(isi, _amplop(_M, _A)) == [KODE_STATUS_TERLARANG]


def test_kata_status_harus_kata_utuh():
    isi = _isi(scenario_assumptions=["Guru sudah terbiasa dengan alreadyx dan approvement"])
    assert aturan_p06(isi, _amplop(_M, _A)) == []


def test_angka_fte_ditagih():
    isi = _isi()
    isi["options"][2]["uraian"] = "Penerima butuh 1,5 FTE tambahan"
    assert aturan_p06(isi, _amplop(_M, _A)) == [KODE_ANGKA_FTE]
    for teks in ("0.5 fte", "2FTE", "3 FTE"):
        assert aturan_p06(_isi(scenario_assumptions=[teks]), _amplop(_M, _A)) == [KODE_ANGKA_FTE]
    assert aturan_p06(_isi(scenario_assumptions=["FTE tidak dihitung"]), _amplop(_M, _A)) == []


def test_source_ids_asing_atau_kosong_rujukan_tak_dikenal():
    isi = _isi()
    isi["options"][0]["fakta_sumber"][0]["source_ids"] = ["bukti:asing"]
    assert aturan_p06(isi, _amplop(_M, _A)) == [KODE_RUJUKAN_TAK_DIKENAL]
    isi = _isi()
    isi["options"][0]["fakta_sumber"][0]["source_ids"] = []
    assert aturan_p06(isi, _amplop(_M, _A)) == [KODE_RUJUKAN_TAK_DIKENAL]


def test_kode_paling_banyak_sekali_dan_urut():
    isi = _isi(scenario_assumptions=["2 FTE", "3 FTE", "READY"])
    isi["options"][0]["fakta_sumber"][0]["source_ids"] = ["x:1"]
    isi["options"][1]["fakta_sumber"][0]["source_ids"] = ["x:2"]
    assert aturan_p06(isi, _amplop(_M, _A)) == [
        KODE_RUJUKAN_TAK_DIKENAL,
        KODE_STATUS_TERLARANG,
        KODE_ANGKA_FTE,
    ]


# --- parameter, katalog, saklar ---


def test_parameter_hanya_kode_dengan_versi_f4_dan_tanpa_kuantitas():
    p = ParameterP06(masalah_id="3f2b8c1e-5d4a-4e6f-9a7b-1c2d3e4f5a6b", periode="2026/27")
    assert p.model_dump() == {
        "masalah_id": "3f2b8c1e-5d4a-4e6f-9a7b-1c2d3e4f5a6b",
        "periode": "2026/27",
        "versi_syarat_f4": VERSI_SYARAT_F4,
        "source_verified_quantities": [],
    }
    assert VERSI_SYARAT_F4 == "sementara-2026-11"
    with pytest.raises(ValidationError):
        ParameterP06(masalah_id="m1", periode="2026/27", source_verified_quantities=["5 jam"])
    with pytest.raises(ValidationError):
        ParameterP06(masalah_id="m1", periode="2026/27", versi_syarat_f4="lain")
    with pytest.raises(ValidationError):
        ParameterP06(masalah_id="m 1", periode="2026/27")
    with pytest.raises(ValidationError):
        ParameterP06(masalah_id="m1", periode="2026/27", catatan="bebas")


def test_katalog_memuat_p06_dan_saklar_bawaan_tidak_berubah():
    assert KATALOG_FUNGSI["P06"] is FUNGSI_P06
    assert ATURAN_ISI["P06"] is aturan_p06
    cfg = Settings(_env_file=None)
    assert cfg.ai_fungsi_aktif == []
    assert cfg.ai_jenis_sumber_diizinkan == ["SINTETIS"]
    daftarkan_fungsi(cfg)
    assert "P06" not in FUNGSI_TERDAFTAR
    daftarkan_fungsi(Settings(_env_file=None, ai_fungsi_aktif=["P06"]))
    assert FUNGSI_TERDAFTAR["P06"] is FUNGSI_P06


def test_instruksi_melarang_fte_status_dan_menyebut_pemetaan():
    teks = FUNGSI_P06.instruksi
    for frasa in ("FTE", "VERIFIED", "READY", "APPROVE", "slot", "unknown_parameters",
                  "Alihkan tugas bersyarat", "Pertahankan"):  # fmt: skip
        assert frasa in teks, frasa


# --- sumber alternatif (murni) ---


def test_sumber_alternatif_hanya_field_yang_diizinkan():
    s = sumber_redesain(
        "alternatif",
        "a-1",
        {"opsi": "Sederhanakan", "keputusan": "Disetujui", "status_telaah": "Siap telaah",
         "gap_penerima": "Belum tahu", "pemutus_kode_orang": "O-0009"},
    )  # fmt: skip
    assert s.source_id == "alternatif:a-1" and s.jenis == "REDESAIN"
    assert s.teks == "opsi: Sederhanakan\ngap_penerima: Belum tahu"
    assert "alternatif:" in AWALAN_SUMBER_REDESAIN
    assert "keputusan" not in FIELD_SUMBER_REDESAIN["alternatif"]


# --- instruksi: tanpa asumsi satu penerima, membaca kesiapan ---


def test_instruksi_p06_tanpa_asumsi_satu_penerima_dan_membaca_kesiapan():
    teks = " ".join(FUNGSI_P06.instruksi.split())
    assert "satu jabatan penerima" not in teks and "Penerima selain satu jabatan" not in teks
    assert "kesiapan:" in teks and "BELUM_DINILAI" in teks and "HOLD" in teks
    assert "NOT_ESTIMABLE" in teks and "nol" in teks
    assert "kesiapan:" in FUNGSI_P06.instruksi and FUNGSI_P06.prompt_version == "p06-2"
    assert "kesiapan:" in AWALAN_SUMBER_REDESAIN
    assert "keputusan_perubahan" not in FIELD_SUMBER_REDESAIN["kesiapan"]
