"""Tes unit fungsi AI P02 (normalisasi tugas): skema isi, aturan isi, parameter, dan katalog.

Data sintetis; tanpa basis data dan tanpa jaringan.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from anjab_abk_backend.ai.fungsi_p02 import (
    FIELD_SUMBER_KATALOG_TI,
    FUNGSI_P02,
    JENIS_SUMBER_KATALOG_TI,
    KODE_RUJUKAN_KURANG,
    KODE_RUJUKAN_TAK_DIKENAL,
    SKEMA_ISI_P02,
    ParameterP02,
    aturan_p02,
    sumber_katalog_ti,
    teks_sumber_katalog_ti,
)
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.guardrail import susun_instruksi
from anjab_abk_backend.ai.katalog import KATALOG_FUNGSI, daftarkan_fungsi
from anjab_abk_backend.ai.keluaran import cek_keluaran, skema_dengan_amplop
from anjab_abk_backend.ai.penyerap_usulan import ATURAN_ISI
from anjab_abk_backend.config import Settings

_KATA_TERLARANG = {
    "if", "then", "else", "minLength", "maxLength", "minItems", "maxItems", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "pattern",
}  # fmt: skip
_NAMA_TERLARANG = ("approve", "setuju", "skor", "keputusan", "putusan")
_S1, _S2 = "uraian:ut-1", "uraian:ut-2"


@pytest.fixture(autouse=True)
def _bersihkan_registri():
    FUNGSI_TERDAFTAR.clear()
    yield
    FUNGSI_TERDAFTAR.clear()


def _isi(**ubah: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "task_candidates": [
            {
                "tindakan": "Menyusun",
                "objek": "rencana pelaksanaan pembelajaran",
                "tujuan": "agar pertemuan terencana",
                "cara": "mengacu kurikulum",
                "output": "dokumen RPP",
                "tingkat": "TASK",
                "source_ids": [_S1],
            }
        ],
        "duplicate_suspicions": [{"source_ids": [_S1, _S2], "alasan": "objek mirip"}],
        "split_merge_rationale": [{"jenis": "PECAH", "source_ids": [_S2], "alasan": "dua output"}],
        "reviewer_questions": ["Apakah RPP disusun per pertemuan?"],
    }
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


def _nama_properti(skema: Any) -> set[str]:
    if isinstance(skema, dict):
        hasil = set(skema.get("properties", {}))
        for v in skema.values():
            hasil |= _nama_properti(v)
        return hasil
    if isinstance(skema, list):
        return set().union(*(_nama_properti(x) for x in skema)) if skema else set()
    return set()


# --- skema isi ---


def test_skema_isi_sah_json_schema_dan_tanpa_kata_kunci_terlarang():
    Draft202012Validator.check_schema(SKEMA_ISI_P02)
    Draft202012Validator.check_schema(skema_dengan_amplop(SKEMA_ISI_P02))
    assert not (_kunci(SKEMA_ISI_P02) & _KATA_TERLARANG)
    for nama in _nama_properti(SKEMA_ISI_P02):
        assert not any(t in nama.casefold() for t in _NAMA_TERLARANG), nama


def test_keluaran_sah_lolos_skema_dan_aturan_tanpa_pelanggaran():
    assert not list(Draft202012Validator(SKEMA_ISI_P02).iter_errors(_isi()))
    assert aturan_p02(_isi(), _amplop(_S1, _S2)) == []


def test_tingkat_di_luar_enum_ditolak_skema():
    isi = _isi()
    isi["task_candidates"][0]["tingkat"] = "PROSES"
    assert list(Draft202012Validator(SKEMA_ISI_P02).iter_errors(isi))


def test_field_tambahan_ditolak_skema():
    isi = _isi(skor=5)
    assert list(Draft202012Validator(SKEMA_ISI_P02).iter_errors(isi))


def test_cek_keluaran_menerima_amplop_p02_lengkap():
    teks = "kode: K1\nuraian: Menyusun RPP"
    sumber = {_S1: (hashlib.sha256(teks.encode()).hexdigest(), teks)}
    isi = _isi(duplicate_suspicions=[], split_merge_rationale=[])
    keluaran = {
        "status": "AI_DRAFT",
        "source_refs": [{"source_id": _S1, "source_hash": sumber[_S1][0]}],
        "cited_spans": [{"source_id": _S1, "span": "Menyusun RPP"}],
        "confidence_reason": "kutipan",
        "unknowns": [],
        "contradictions": [],
        "human_review_required": True,
        "isi": isi,
    }
    hasil = cek_keluaran(json.dumps(keluaran), skema_dengan_amplop(SKEMA_ISI_P02), sumber)
    assert hasil.status_qa == "LOLOS", hasil.kode


# --- aturan isi ---


@pytest.mark.parametrize(
    "kunci,indeks",
    [("task_candidates", 0), ("duplicate_suspicions", 0), ("split_merge_rationale", 0)],
)
def test_source_ids_tak_dikenal_melanggar_rujukan(kunci, indeks):
    isi = _isi()
    isi[kunci][indeks]["source_ids"] = [*isi[kunci][indeks]["source_ids"], "uraian:asing"]
    assert aturan_p02(isi, _amplop(_S1, _S2)) == [KODE_RUJUKAN_TAK_DIKENAL]


def test_rujukan_tak_dikenal_dilaporkan_sekali_tanpa_teks():
    isi = _isi()
    for kunci in ("task_candidates", "split_merge_rationale"):
        isi[kunci][0]["source_ids"] = ["uraian:asing"]
    assert aturan_p02(isi, _amplop(_S1, _S2)) == [KODE_RUJUKAN_TAK_DIKENAL]


def test_amplop_tanpa_source_refs_membuat_semua_rujukan_tak_dikenal():
    assert aturan_p02(_isi(), {}) == [KODE_RUJUKAN_TAK_DIKENAL]


def test_jumlah_rujukan_kurang_dari_batas():
    tanpa = _isi()
    tanpa["task_candidates"][0]["source_ids"] = []
    assert aturan_p02(tanpa, _amplop(_S1, _S2)) == [KODE_RUJUKAN_KURANG]
    satu = _isi(duplicate_suspicions=[{"source_ids": [_S1, _S1], "alasan": "x"}])
    assert aturan_p02(satu, _amplop(_S1, _S2)) == [KODE_RUJUKAN_KURANG]


def test_daftar_kosong_tanpa_pelanggaran():
    isi = _isi(task_candidates=[], duplicate_suspicions=[], split_merge_rationale=[])
    assert aturan_p02(isi, {}) == []


def test_aturan_tidak_mengubah_isi():
    isi = _isi()
    salinan = copy.deepcopy(isi)
    aturan_p02(isi, _amplop(_S1))
    assert isi == salinan


def test_aturan_p02_terdaftar_di_aturan_isi():
    assert ATURAN_ISI["P02"] is aturan_p02


# --- parameter dan sumber katalog ---


def test_parameter_hanya_kode_tanpa_teks_bebas():
    p = ParameterP02(jabatan_kode="GURU-SD", unit=None, periode="2026/27")
    harapan = {"jabatan_kode": "GURU-SD", "unit": None, "periode": "2026/27"}
    assert p.model_dump(mode="json") == harapan
    for buruk in ({"jabatan_kode": "guru sd"}, {"unit": "S D"}, {"periode": "2026/27 ganjil"}):
        with pytest.raises(ValidationError):
            ParameterP02(**{"jabatan_kode": "G", "unit": "SD", "periode": "2026-27", **buruk})
    with pytest.raises(ValidationError):
        ParameterP02(jabatan_kode="G", periode="2026", catatan="x")  # type: ignore[call-arg]


def test_teks_sumber_hanya_field_tugas_dan_standar():
    nilai = {
        "kode": "K1", "unit": "SD", "tugas_pokok": "Perencanaan", "detil_tugas": None,
        "uraian": "Menyusun  RPP", "std_va_type": "VA-Core", "std_jam_per_minggu": 2.5,
        "jabatan_id": "jbt_rahasia", "urutan": 7, "catatan_internal": "jangan dikirim",
    }  # fmt: skip
    teks = teks_sumber_katalog_ti(nilai)
    kunci = [b.split(":", 1)[0] for b in teks.splitlines()]
    assert set(kunci) <= set(FIELD_SUMBER_KATALOG_TI)
    assert kunci == ["kode", "unit", "tugas_pokok", "uraian", "std_jam_per_minggu", "std_va_type"]
    assert "jbt_rahasia" not in teks and "jangan dikirim" not in teks
    assert "uraian: Menyusun RPP" in teks


def test_sumber_katalog_ti_berjenis_dan_berhash():
    s = sumber_katalog_ti("ut-9", {"kode": "K9", "uraian": "Mengajar"})
    assert s.source_id == "uraian:ut-9" and s.jenis == JENIS_SUMBER_KATALOG_TI == "KATALOG_TI"
    assert s.source_hash == hashlib.sha256(s.teks.encode()).hexdigest()


# --- instruksi dan katalog ---


def test_instruksi_memuat_larangan_body():
    ins = FUNGSI_P02.instruksi
    assert "bukan pekerjaan aktual yang tervalidasi" in ins
    assert "Narasi asal tidak diubah" in ins
    assert "Kemiripan teks bukan bukti duplikasi" in ins
    assert "DUTY" in ins and "TASK" in ins and "ACTIVITY" in ins
    assert "bahasa Indonesia" in ins
    assert susun_instruksi(ins).endswith(ins)


def test_katalog_memuat_p02_dan_bawaan_tidak_aktif():
    assert KATALOG_FUNGSI["P02"] is FUNGSI_P02
    assert Settings(_env_file=None).ai_fungsi_aktif == []
    assert Settings(_env_file=None).ai_jenis_sumber_diizinkan == ["SINTETIS"]
    daftarkan_fungsi(Settings(ai_fungsi_aktif=[]))
    assert "P02" not in FUNGSI_TERDAFTAR
    daftarkan_fungsi(Settings(ai_fungsi_aktif=["P02"]))
    assert FUNGSI_TERDAFTAR == {"P02": FUNGSI_P02}
