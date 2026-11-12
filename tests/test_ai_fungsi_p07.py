"""Tes unit fungsi AI P07 (kartu keputusan): skema, aturan isi, parameter, katalog, otorisasi.

Data sintetis; tanpa basis data dan tanpa jaringan.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from anjab_abk_backend.ai.fungsi_p06 import memuat_status_terlarang
from anjab_abk_backend.ai.fungsi_p07 import (
    FUNGSI_P07,
    KODE_CHANGE_TIDAK_DISEBUT,
    KODE_RUJUKAN_TAK_DIKENAL,
    KODE_STATUS_TERLARANG,
    KODE_UNKNOWNS_KOSONG,
    SKEMA_ISI_P07,
    ParameterP07,
    aturan_p07,
)
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.katalog import KATALOG_FUNGSI, daftarkan_fungsi
from anjab_abk_backend.ai.keluaran import skema_dengan_amplop
from anjab_abk_backend.ai.otorisasi_redesain import sumber_otorisasi
from anjab_abk_backend.ai.penyerap_usulan import ATURAN_ISI
from anjab_abk_backend.ai.syarat_f4 import VERSI_SYARAT_F4
from anjab_abk_backend.config import Settings

_KATA_TERLARANG = {
    "if", "then", "else", "minLength", "maxLength", "maxItems", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "pattern",
}  # fmt: skip
_M = "masalah:m-1"
_B = "bukti:b-1"
_A = "alternatif:a-1"
_O = "otorisasi:m-1"


@pytest.fixture(autouse=True)
def _bersihkan_registri():
    FUNGSI_TERDAFTAR.clear()
    yield
    FUNGSI_TERDAFTAR.clear()


def _isi(**ubah: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "decision_card": {
            "masalah": "Rekap nilai terlambat diserahkan ke wali kelas",
            "bukti": [{"pernyataan": "Ada tiga format lembar nilai", "source_ids": [_M, _B]}],
            "alternatif": [{"ringkasan": "Satukan format lembar nilai", "source_ids": [_A]}],
            "batas_angka": "Lama penyalinan per kelas belum diukur",
            "risiko": ["Lembar lama masih beredar"],
            "persyaratan": ["Uji format pada satu kelas dulu"],
        },
        "limitation": ["Kartu belum memuat penerima tugas lengkap"],
        "required_signoffs": [
            {"jenis": "PRIORITY", "pihak": "Yayasan", "status": "BELUM_DITANDATANGANI"},
            {"jenis": "CHANGE", "pihak": "Yayasan", "status": "BELUM_DITANDATANGANI"},
        ],
    }  # fmt: skip
    d.update(ubah)
    return d


def _amplop(*ids: str, unknowns: list[str] | None = None) -> dict[str, Any]:
    return {
        "source_refs": [{"source_id": i, "source_hash": "a" * 64} for i in ids],
        "unknowns": ["Penerima tugas lengkap belum diketahui"] if unknowns is None else unknowns,
    }


def _galat(isi: dict[str, Any]) -> list:
    return list(Draft202012Validator(SKEMA_ISI_P07).iter_errors(isi))


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


def test_skema_sah_tanpa_authorization_state_tanpa_angka_minitems_hanya_limitation():
    Draft202012Validator.check_schema(SKEMA_ISI_P07)
    Draft202012Validator.check_schema(skema_dengan_amplop(SKEMA_ISI_P07))
    simpul = _simpul(SKEMA_ISI_P07)
    for jalur, n in simpul:
        assert not (_KATA_TERLARANG & set(n)), jalur
        if n.get("type") == "object":
            assert n["additionalProperties"] is False, jalur
            assert set(n["required"]) == set(n["properties"]), jalur
    assert not [j for j, n in simpul if n.get("type") in ("number", "integer")]
    assert [(j, n["minItems"]) for j, n in simpul if "minItems" in n] == [
        ("/properties/limitation", 1)
    ]
    nama = {k for _, n in simpul for k in (n.get("properties") or {})}
    assert "authorization_state" not in nama
    assert "authorization_state" not in json.dumps(SKEMA_ISI_P07)


def test_positif_keluaran_sah_lolos_skema_dan_aturan_isi():
    isi = _isi()
    assert _galat(isi) == []
    assert aturan_p07(isi, _amplop(_M, _B, _A, _O)) == []


def test_negatif_kunci_authorization_state_ditolak_skema():
    isi = _isi(authorization_state={"change_ditandatangani": True})
    assert _galat(isi)
    kartu = copy.deepcopy(_isi())
    kartu["decision_card"]["authorization_state"] = {"status": "DISETUJUI"}
    assert _galat(kartu)


def test_skema_menolak_status_signoff_selain_belum_ditandatangani_dan_limitation_kosong():
    isi = _isi()
    isi["required_signoffs"][1]["status"] = "DITANDATANGANI"
    assert _galat(isi)
    isi = _isi()
    isi["required_signoffs"][0]["jenis"] = "BUDGET"
    assert _galat(isi)
    assert _galat(_isi(limitation=[]))


# --- aturan isi ---


def test_negatif_tanpa_signoff_change_ditolak_aturan():
    isi = _isi(
        required_signoffs=[
            {"jenis": "PRIORITY", "pihak": "Yayasan", "status": "BELUM_DITANDATANGANI"}
        ]
    )
    assert _galat(isi) == []
    assert aturan_p07(isi, _amplop(_M, _B, _A)) == [KODE_CHANGE_TIDAK_DISEBUT]


def test_negatif_status_approve_di_teks_ditolak_aturan():
    isi = _isi()
    isi["decision_card"]["persyaratan"] = ["Alternatif ini sudah APPROVE oleh Yayasan"]
    assert aturan_p07(isi, _amplop(_M, _B, _A)) == [KODE_STATUS_TERLARANG]
    isi["decision_card"]["persyaratan"] = ["Readymade format tersedia"]
    assert aturan_p07(isi, _amplop(_M, _B, _A)) == []


def test_rujukan_tak_dikenal_atau_kosong():
    isi = _isi()
    isi["decision_card"]["bukti"][0]["source_ids"] = ["bukti:asing"]
    assert aturan_p07(isi, _amplop(_M, _B, _A)) == [KODE_RUJUKAN_TAK_DIKENAL]
    isi = _isi()
    isi["decision_card"]["alternatif"][0]["source_ids"] = []
    assert aturan_p07(isi, _amplop(_M, _B, _A)) == [KODE_RUJUKAN_TAK_DIKENAL]


def test_unknowns_kosong_dan_urutan_kode():
    assert aturan_p07(_isi(), _amplop(_M, _B, _A, unknowns=[])) == [KODE_UNKNOWNS_KOSONG]
    isi = _isi(required_signoffs=[])
    isi["decision_card"]["bukti"][0]["source_ids"] = []
    isi["decision_card"]["risiko"] = ["Status VERIFIED"]
    assert aturan_p07(isi, {"source_refs": []}) == [
        KODE_RUJUKAN_TAK_DIKENAL,
        KODE_STATUS_TERLARANG,
        KODE_CHANGE_TIDAK_DISEBUT,
        KODE_UNKNOWNS_KOSONG,
    ]


def test_aturan_status_terlarang_dipakai_bersama_p06():
    assert KODE_STATUS_TERLARANG == "STATUS_TERLARANG"
    assert memuat_status_terlarang({"x": ["siap ready"]})
    assert not memuat_status_terlarang({"APPROVE": ["tanpa kata status"]})


# --- katalog, parameter, otorisasi ---


def test_p07_di_katalog_aturan_terdaftar_dan_bawaan_nonaktif():
    assert KATALOG_FUNGSI["P07"] is FUNGSI_P07
    assert FUNGSI_P07.skema_isi is SKEMA_ISI_P07
    assert ATURAN_ISI["P07"] is aturan_p07
    cfg = Settings(_env_file=None)
    assert cfg.ai_fungsi_aktif == []
    daftarkan_fungsi(cfg)
    assert "P07" not in FUNGSI_TERDAFTAR
    daftarkan_fungsi(Settings(_env_file=None, ai_fungsi_aktif=["P07"]))
    assert FUNGSI_TERDAFTAR == {"P07": FUNGSI_P07}


def test_parameter_hanya_kode_dan_versi_f4():
    p = ParameterP07(masalah_id="m-1", periode="2026/27")
    assert p.model_dump() == {
        "masalah_id": "m-1",
        "periode": "2026/27",
        "versi_syarat_f4": VERSI_SYARAT_F4,
        "usulan_p06_id": None,
    }
    with pytest.raises(ValidationError):
        ParameterP07(masalah_id="m-1", periode="2026/27", authorization_state={})
    with pytest.raises(ValidationError):
        ParameterP07(masalah_id="m-1", periode="2026/27", usulan_p06_id="bukan uuid")


def test_sumber_otorisasi_tanpa_diambil_pada_dan_hash_stabil():
    state = {
        "alternatif": [{"alternatif_id": "a-1", "status_telaah": "Siap telaah"}],
        "prioritas_final": "P1 - Utama",
        "change_ditandatangani": False,
        "sumber": "server",
        "diambil_pada": "2026-11-09T00:00:00+00:00",
    }
    s1 = sumber_otorisasi("m-1", state)
    s2 = sumber_otorisasi("m-1", {**state, "diambil_pada": "2027-01-01T00:00:00+00:00"})
    assert s1.source_id == _O and s1.jenis == "REDESAIN"
    assert "diambil_pada" not in s1.teks and "P1 - Utama" in s1.teks
    assert s1.source_hash == s2.source_hash


def test_instruksi_p07_tanpa_asumsi_penerima_tunggal_dan_membaca_kesiapan():
    teks = " ".join(FUNGSI_P07.instruksi.split())
    assert "Penerima tugas selain yang tercatat" not in teks
    assert "kesiapan:" in teks and "BELUM_DINILAI" in teks and "NOT_ESTIMABLE" in teks
    assert "persyaratan" in teks and "BELUM_DIPUTUS" in teks
    assert "PRIORITY dan CHANGE secara terpisah" in teks  # aturan 2 & 3 tak berubah
    assert "jangan memberi status VERIFIED, READY, atau APPROVE" in teks
    assert FUNGSI_P07.prompt_version == "p07-2"
