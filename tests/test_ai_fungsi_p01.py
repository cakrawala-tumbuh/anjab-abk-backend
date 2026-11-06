"""Test fungsi AI P01 (ekstraksi fakta dari dokumen sumber): skema, instruksi, parameter."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest
from pydantic import ValidationError

from anjab_abk_backend.ai.fungsi_p01 import (
    FUNGSI_P01,
    PENILAIAN_SUMBER_P01,
    SIFAT_FAKTA_P01,
    SKEMA_ISI_P01,
    ParameterP01,
    aturan_p01,
)
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.guardrail import susun_instruksi
from anjab_abk_backend.ai.katalog import KATALOG_FUNGSI, daftarkan_fungsi
from anjab_abk_backend.ai.keluaran import cek_keluaran, skema_dengan_amplop
from anjab_abk_backend.config import Settings

_TEKS = "SOP Penyusunan Perangkat Ajar. Guru wajib menyusun perangkat ajar sebelum semester."
_SUMBER = {"s1": (hashlib.sha256(_TEKS.encode()).hexdigest(), _TEKS)}
_SKEMA = skema_dengan_amplop(FUNGSI_P01.skema_isi)
_KATA_TERLARANG = {
    "if", "then", "else", "minLength", "maxLength", "minItems", "maxItems", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "pattern",
}  # fmt: skip
_NAMA_TERLARANG = ("approve", "setuju", "skor", "keputusan", "putusan")


@pytest.fixture(autouse=True)
def _bersihkan_registri():
    FUNGSI_TERDAFTAR.clear()
    yield
    FUNGSI_TERDAFTAR.clear()


def _isi(**ubah: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "factual_extracts": [
            {
                "fakta": "Guru wajib menyusun perangkat ajar.",
                "sifat": "NORMATIF",
                "source_id": "s1",
                "span": "Guru wajib menyusun perangkat ajar",
            }
        ],
        "source_quality": [{"source_id": "s1", "penilaian": "CUKUP", "alasan": "teks utuh"}],
        "uncertainties": [],
        "limitations": ["hanya satu dokumen"],
    }
    d.update(ubah)
    return d


def _amplop(isi: dict[str, Any], **ubah: Any) -> str:
    d: dict[str, Any] = {
        "status": "AI_DRAFT",
        "source_refs": [{"source_id": "s1", "source_hash": _SUMBER["s1"][0]}],
        "cited_spans": [{"source_id": "s1", "span": "Guru wajib menyusun perangkat ajar"}],
        "confidence_reason": "kutipan langsung",
        "unknowns": [],
        "contradictions": [],
        "human_review_required": True,
        "isi": isi,
    }
    d.update(ubah)
    return json.dumps(d)


def _telusuri(skema: Any):
    if isinstance(skema, dict):
        yield skema
        for v in skema.values():
            yield from _telusuri(v)
    elif isinstance(skema, list):
        for v in skema:
            yield from _telusuri(v)


def _nama_properti(skema: Any):
    for node in _telusuri(skema):
        props = node.get("properties")
        if isinstance(props, dict):
            yield from props


def test_skema_rekursif_tanpa_kata_terlarang_dan_objek_tertutup():
    for skema in (SKEMA_ISI_P01, _SKEMA):
        for node in _telusuri(skema):
            assert not (_KATA_TERLARANG & node.keys()), node
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
    assert set(SKEMA_ISI_P01["required"]) == {
        "factual_extracts", "source_quality", "uncertainties", "limitations",
    }  # fmt: skip
    assert FUNGSI_P01.kode == "P01" and FUNGSI_P01.prompt_version == "p01-1"


def test_nama_field_tanpa_persetujuan_skor_atau_keputusan_pada_semua_kedalaman():
    nama = list(_nama_properti(SKEMA_ISI_P01))
    # field bersarang di dalam larik: pastikan penelusuran memang menjangkaunya.
    assert {"factual_extracts", "fakta", "sifat", "span", "penilaian", "alasan"} <= set(nama)
    for n in nama:
        assert not any(k in n.casefold() for k in _NAMA_TERLARANG), n
    assert "qa_flags" not in nama  # milik server (kode_qa), bukan skema


def test_telusur_nama_menangkap_pelanggaran_bersarang():
    """Penjaga penjaga: field terlarang di kedalaman ketiga tertangkap oleh penelusur."""
    skema = {
        "type": "object",
        "properties": {
            "a": {"type": "array", "items": {"type": "object", "properties": {"skor_akhir": {}}}}
        },
    }
    assert "skor_akhir" in set(_nama_properti(skema))


def test_enum_sifat_dan_penilaian():
    item = SKEMA_ISI_P01["properties"]["factual_extracts"]["items"]
    assert item["properties"]["sifat"]["enum"] == ["NORMATIF", "DESKRIPTIF_DOKUMEN"]
    assert tuple(item["properties"]["sifat"]["enum"]) == SIFAT_FAKTA_P01
    kualitas = SKEMA_ISI_P01["properties"]["source_quality"]["items"]
    assert kualitas["properties"]["penilaian"]["enum"] == ["CUKUP", "TERBATAS", "TIDAK_JELAS"]
    assert tuple(kualitas["properties"]["penilaian"]["enum"]) == PENILAIAN_SUMBER_P01


def test_keluaran_sah_lolos_dan_gap_evidence_gap():
    h = cek_keluaran(_amplop(_isi()), _SKEMA, _SUMBER)
    assert (h.status_qa, h.kode) == ("LOLOS", ())
    gap = _amplop(
        _isi(factual_extracts=[], source_quality=[]),
        status="EVIDENCE_GAP",
        cited_spans=[],
        source_refs=[],
        unknowns=["sumber tidak memuat prosedur"],
    )
    h2 = cek_keluaran(gap, _SKEMA, _SUMBER)
    assert (h2.status_qa, h2.kode) == ("EVIDENCE_GAP", ())
    tanpa_alasan = _amplop(
        _isi(factual_extracts=[]), status="EVIDENCE_GAP", cited_spans=[], unknowns=[]
    )
    assert cek_keluaran(tanpa_alasan, _SKEMA, _SUMBER).kode == ("GAP_TANPA_ALASAN",)


def test_sifat_di_luar_enum_skema_tidak_sah():
    fakta = [{"fakta": "x", "sifat": "TERLAKSANA", "source_id": "s1", "span": "Guru wajib"}]
    h = cek_keluaran(_amplop(_isi(factual_extracts=fakta)), _SKEMA, _SUMBER)
    assert (h.status_qa, h.kode) == ("KARANTINA", ("SKEMA_TIDAK_SAH",))


def test_penilaian_di_luar_enum_skema_tidak_sah():
    kualitas = [{"source_id": "s1", "penilaian": "BAGUS", "alasan": "x"}]
    h = cek_keluaran(_amplop(_isi(source_quality=kualitas)), _SKEMA, _SUMBER)
    assert (h.status_qa, h.kode) == ("KARANTINA", ("SKEMA_TIDAK_SAH",))


@pytest.mark.parametrize("tambah", ["approve", "setuju", "skor", "keputusan", "peran"])
def test_field_persetujuan_atau_asing_ditolak_skema(tambah):
    isi = _isi()
    isi[tambah] = True
    assert cek_keluaran(_amplop(isi), _SKEMA, _SUMBER).kode == ("SKEMA_TIDAK_SAH",)


def test_field_bersarang_ditolak_skema_dan_field_wajib_hilang_ditolak():
    isi = _isi()
    isi["factual_extracts"][0]["skor"] = 3
    assert cek_keluaran(_amplop(isi), _SKEMA, _SUMBER).kode == ("SKEMA_TIDAK_SAH",)
    isi2 = _isi()
    del isi2["limitations"]
    assert cek_keluaran(_amplop(isi2), _SKEMA, _SUMBER).kode == ("SKEMA_TIDAK_SAH",)


def test_sitasi_palsu_fiktif_dan_kosong_dikarantina():
    palsu = _amplop(_isi(), cited_spans=[{"source_id": "s1", "span": "kalimat karangan model"}])
    assert cek_keluaran(palsu, _SKEMA, _SUMBER).kode == ("KUTIPAN_TIDAK_DITEMUKAN",)
    fiktif = _amplop(_isi(), cited_spans=[{"source_id": "s9", "span": "x"}])
    assert cek_keluaran(fiktif, _SKEMA, _SUMBER).kode == ("SUMBER_FIKTIF",)
    kosong = _amplop(_isi(), cited_spans=[])
    assert cek_keluaran(kosong, _SKEMA, _SUMBER).kode == ("TANPA_SITASI",)


def test_parameter_sah_dan_menolak_teks_bebas():
    p = ParameterP01(peran_ref="guru", periode="2026-27")
    assert p.model_dump() == {"peran_ref": "guru", "periode": "2026-27"}
    assert ParameterP01(peran_ref="GURU_kelas.1:a-b", periode="2026-S1").peran_ref
    with pytest.raises(ValidationError):
        ParameterP01(peran_ref="guru", periode="2026-27", lain="x")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ParameterP01(peran_ref="guru")  # type: ignore[call-arg]


@pytest.mark.parametrize(
    "buruk",
    [
        "", "tahun ajaran", "a b", " a", "a ", "a\nb", "a\n", "\n", "a\r", "a\tb", "a\x00",
        "a;b", "a,b", "a$", "<b>", "é", "x" * 101, "teks bebas tentang murid",
    ],
)  # fmt: skip
@pytest.mark.parametrize("kolom", ["peran_ref", "periode"])
def test_parameter_menolak_spasi_newline_karakter_terlarang_dan_panjang(kolom, buruk):
    nilai = {"peran_ref": "guru", "periode": "2026-27", kolom: buruk}
    with pytest.raises(ValidationError):
        ParameterP01(**nilai)


def test_parameter_periode_menerima_garis_miring_tapi_peran_ref_tidak():
    assert ParameterP01(peran_ref="guru", periode="2026/27").periode == "2026/27"
    with pytest.raises(ValidationError):
        ParameterP01(peran_ref="a/b", periode="2026-27")
    with pytest.raises(ValidationError):
        ParameterP01(peran_ref="guru", periode="2026/27 ganjil")


def test_parameter_menerima_panjang_maksimum():
    assert ParameterP01(peran_ref="x" * 100, periode="y" * 100)


def test_instruksi_memuat_setiap_larangan_body():
    ins = FUNGSI_P01.instruksi
    assert "Ambil hanya yang tertulis di sumber" in ins
    assert "Dokumen normatif" in ins and "menunjukkan yang seharusnya, bukan yang terlaksana" in ins
    assert "NORMATIF" in ins and "DESKRIPTIF_DOKUMEN" in ins
    assert "Anda tidak mengarang angka" in ins
    assert "Tiap fakta punya kutipan" in ins and "cited_spans" in ins
    assert "tidak mengisi persetujuan, skor, atau keputusan" in ins
    assert "EVIDENCE_GAP" in ins and "unknowns" in ins
    assert "factual_extracts" in ins and "daftar kosong" in ins
    assert susun_instruksi(ins).endswith(ins)


def test_katalog_memuat_p01_dan_terdaftar_hanya_bila_disebut():
    assert KATALOG_FUNGSI["P01"] is FUNGSI_P01
    daftarkan_fungsi(Settings(ai_fungsi_aktif=[]))
    assert "P01" not in FUNGSI_TERDAFTAR
    daftarkan_fungsi(Settings(ai_fungsi_aktif=["P01"]))
    assert FUNGSI_TERDAFTAR == {"P01": FUNGSI_P01}


# --- aturan_p01 ---


def _fakta(span: str, source_id: str = "s1") -> dict[str, Any]:
    return {"fakta": "f", "sifat": "NORMATIF", "source_id": source_id, "span": span}


def _amplop_cited(*pasangan: tuple[str, str]) -> dict[str, Any]:
    return {"cited_spans": [{"source_id": sid, "span": sp} for sid, sp in pasangan]}


def test_aturan_p01_span_sama_setelah_spasi_dinormalkan_lolos():
    isi = {"factual_extracts": [_fakta("Guru  wajib\nmenyusun")]}
    assert aturan_p01(isi, _amplop_cited(("s1", " Guru wajib menyusun "))) == []


def test_aturan_p01_span_potongan_kutipan_lebih_panjang_lolos():
    isi = {"factual_extracts": [_fakta("wajib menyusun")]}
    assert aturan_p01(isi, _amplop_cited(("s1", "Guru wajib menyusun perangkat"))) == []


def test_aturan_p01_tanpa_fakta_lolos():
    assert aturan_p01({"factual_extracts": []}, _amplop_cited()) == []


@pytest.mark.parametrize(
    ("fakta", "kutipan"),
    [
        (_fakta("karangan model"), [("s1", "Guru wajib menyusun")]),
        (_fakta("Guru wajib menyusun", "s2"), [("s1", "Guru wajib menyusun")]),
        (_fakta("   "), [("s1", "Guru wajib menyusun")]),
        (_fakta("guru wajib"), [("s1", "Guru wajib menyusun")]),  # peka huruf besar-kecil
    ],
)
def test_aturan_p01_fakta_tak_terbukti_satu_kode(fakta, kutipan):
    assert aturan_p01({"factual_extracts": [fakta]}, _amplop_cited(*kutipan)) == [
        "SPAN_FAKTA_TIDAK_DITEMUKAN"
    ]


def test_aturan_p01_dua_fakta_melanggar_kode_sekali():
    isi = {"factual_extracts": [_fakta("palsu satu"), _fakta("palsu dua")]}
    assert aturan_p01(isi, _amplop_cited(("s1", "Guru"))) == ["SPAN_FAKTA_TIDAK_DITEMUKAN"]
