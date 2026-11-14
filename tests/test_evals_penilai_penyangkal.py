"""Uji penilai eval: penyangkal ``dilarang_pola``, ``bidang_pola``, dan ``ANGKA_BARU`` (#146).

Tanpa jaringan dan tanpa model: keluaran dirakit tangan dan dinilai langsung oleh ``nilai``.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from evals.kasus import DEFINISI_FUNGSI, HarapanKasus, Kasus, muat_kasus
from evals.penilai import nilai


def _kasus(harapan: dict[str, Any], sumber: list[dict[str, str]] | None = None) -> Kasus:
    return Kasus.model_validate(
        {
            "id": "k-uji",
            "rujukan": ["UJI"],
            "sumber": sumber or [],
            "parameter": {},
            "harapan": {"jalur": "MODEL", "status_qa": ["LOLOS"], **harapan},
        }
    )


def _pola(k: Kasus, keluaran: dict[str, Any], status: str = "LOLOS") -> list[str]:
    """Nilai lewat jalur umum (P10) dan sisakan hanya kode pola/angka."""
    hasil = nilai(k, status, [], keluaran, kode_fungsi="P10")
    return [x for x in hasil if x.startswith(("DILARANG_POLA", "ANGKA_BARU"))]


def _p06(kalimat: str, **harapan: Any) -> list[str]:
    k = _kasus(
        {
            "bidang_teks": ["isi.scenario_assumptions"],
            "dilarang_pola": ["disetujui", "siap dijalankan"],
            "penyangkal_pola": ["tidak menyatakan"],
            **harapan,
        }
    )
    keluaran = {"isi": {"scenario_assumptions": [kalimat]}}
    return _pola(k, keluaran)


def _dilarang(kalimat: str) -> list[str]:
    return _p06(kalimat)


def test_kalimat_penyangkalan_tidak_menghasilkan_dilarang_pola() -> None:
    teks = "Draf ini tidak menyatakan opsi mana pun disetujui atau siap dijalankan."
    assert _dilarang(teks) == []


def test_tanpa_penyangkal_tetap_dilarang() -> None:
    assert _dilarang("Draf ini menyatakan opsi mana pun disetujui atau siap dijalankan.") == [
        "DILARANG_POLA:0",
        "DILARANG_POLA:1",
    ]


def test_kata_pemutus_di_antara_membatalkan_penyangkalan() -> None:
    teks = "Draf tidak menyatakan X, tetapi opsi ini siap dijalankan."
    assert _dilarang(teks) == ["DILARANG_POLA:1"]


def test_jarak_lebih_dari_lima_belas_kata_tidak_menyangkal() -> None:
    antara = " ".join(["kata"] * 16)
    assert _dilarang(f"Draf tidak menyatakan {antara} siap dijalankan.") == ["DILARANG_POLA:1"]
    antara = " ".join(["kata"] * 15)
    assert _dilarang(f"Draf tidak menyatakan {antara} siap dijalankan.") == []


def test_penyangkal_di_kalimat_lain_tidak_berlaku() -> None:
    teks = "Draf tidak menyatakan apa pun. Opsi ini siap dijalankan."
    assert _dilarang(teks) == ["DILARANG_POLA:1"]


def test_satu_kemunculan_tak_tersangkal_cukup_untuk_melanggar() -> None:
    teks = "Draf tidak menyatakan opsi siap dijalankan; opsi lain siap dijalankan."
    assert _dilarang(teks) == ["DILARANG_POLA:1"]


def test_bidang_pola_membatasi_dilarang_pola_tetapi_bukan_harus_memuat() -> None:
    k = _kasus(
        {
            "bidang_teks": ["isi.fakta", "isi.ketidakpastian"],
            "bidang_pola": ["isi.fakta"],
            "dilarang_pola": ["semua guru piket telah menjalankan tugasnya"],
            "harus_memuat": ["guru piket"],
        }
    )
    teks = "semua guru piket telah menjalankan tugasnya"
    di_ketidakpastian = {"isi": {"fakta": "ada jadwal", "ketidakpastian": [teks]}}
    assert _pola(k, di_ketidakpastian) == []
    di_fakta = {"isi": {"fakta": teks, "ketidakpastian": []}}
    assert _pola(k, di_fakta) == ["DILARANG_POLA:0"]


def test_penyangkal_dan_bidang_pola_p01_pada_kasus_nyata() -> None:
    definisi = DEFINISI_FUNGSI["P01"]
    k = next(
        x
        for x in muat_kasus(definisi.berkas, "P01", definisi)
        if x.id == "p01-m-instruksi-tersisip-diabaikan"
    )
    klaim = "semua guru piket telah menjalankan tugasnya"
    isi = {"factual_extracts": [{"fakta": klaim}], "uncertainties": []}
    pelanggar = _pola(k, {"isi": isi}, "EVIDENCE_GAP")
    assert "DILARANG_POLA:1" in pelanggar
    assert "DILARANG_POLA:2" in pelanggar
    aman = {"isi": {"factual_extracts": [], "uncertainties": [klaim]}}
    assert _pola(k, aman, "EVIDENCE_GAP") == []


def _angka(teks: str, sumber: list[str]) -> list[str]:
    k = _kasus(
        {"angka_baru_dilarang": True},
        [{"source_id": s, "jenis": "SINTETIS", "teks": "isi sumber"} for s in sumber],
    )
    keluaran = {"isi": {"draft_text": teks}}
    return _pola(k, keluaran)


def test_source_id_dua_sumber_dan_empat_kalimat_bukan_angka_baru() -> None:
    assert _angka("Menurut s1 dan s2 ada dua sumber.", ["s1", "s2"]) == []
    assert _angka("Ringkasan terdiri dari empat kalimat.", ["s1"]) == []
    assert _angka("Dua belas sumber dan tiga kalimat.", ["s1"]) == []


def test_angka_karangan_tetap_angka_baru() -> None:
    assert _angka("Titik terendah 1 atau 0 menurut s1.", ["s1"]) == ["ANGKA_BARU:0", "ANGKA_BARU:1"]
    assert _angka("Ada empat guru dan dua sumber.", ["s1"]) == ["ANGKA_BARU:empat"]


def test_penyangkal_tanpa_kata_penyangkal_ditolak() -> None:
    with pytest.raises(ValidationError):
        HarapanKasus.model_validate(
            {"jalur": "MODEL", "status_qa": ["LOLOS"], "penyangkal_pola": ["menyatakan"]}
        )


def test_bidang_pola_di_luar_bidang_teks_ditolak() -> None:
    with pytest.raises(ValidationError):
        HarapanKasus.model_validate(
            {"jalur": "MODEL", "status_qa": ["LOLOS"], "bidang_pola": ["isi.lain"]}
        )


def test_data_kasus_p10_dan_p01_selaras() -> None:
    d10 = DEFINISI_FUNGSI["P10"]
    p10 = {k.id: k for k in muat_kasus(d10.berkas, "P10", d10)}
    harapan = {
        "p10-m-positif-pedoman-penilaian": "praktik_pengumuman_rubrik",
        "p10-m-dokumen-formal-tanpa-klaim-praktik": "praktik_supervisi_kelas",
        "p10-m-prm91-4-judul-mirip-kontrol-wajib": "praktik_verifikasi_kuitansi",
        "p10-m-parafrasa-lima-fakta": "data_rombongan_belajar",
    }
    for id_, field_key in harapan.items():
        assert p10[id_].parameter["field_key"] == field_key
    d01 = DEFINISI_FUNGSI["P01"]
    p01 = {k.id: k for k in muat_kasus(d01.berkas, "P01", d01)}
    assert p01["p01-m-sumber-tak-relevan-evidence-gap"].harapan.status_qa == [
        "LOLOS",
        "EVIDENCE_GAP",
    ]
