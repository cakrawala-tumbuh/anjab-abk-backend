"""Test fungsi AI P04 (pengusul pertanyaan bukti): skema, aturan, parameter, instruksi, katalog."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from anjab_abk_backend.ai.fungsi_p01 import aturan_p01
from anjab_abk_backend.ai.fungsi_p04 import (
    FUNGSI_P04,
    SKEMA_ISI_P04,
    ParameterP04,
    aturan_p04,
    id_sumber_keputusan,
    id_sumber_klaim,
)
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.guardrail import susun_instruksi
from anjab_abk_backend.ai.katalog import KATALOG_FUNGSI, daftarkan_fungsi
from anjab_abk_backend.ai.keluaran import cek_keluaran, skema_dengan_amplop
from anjab_abk_backend.ai.penyerap_usulan import ATURAN_ISI
from anjab_abk_backend.ai.redaksi import SumberAi, gerbang_masukan
from anjab_abk_backend.config import Settings

_KLAIM = "Guru mengikuti pelatihan penyusunan soal."
_KEPUTUSAN = "Menetapkan apakah pelatihan lanjutan diperlukan."
_SID_KLAIM = id_sumber_klaim(_KLAIM)
_SID_KEPUTUSAN = id_sumber_keputusan(_KEPUTUSAN)
_SUMBER = {
    "s1": ("h1", "Kepala sekolah menetapkan jadwal rapat guru setiap hari Senin."),
    _SID_KLAIM: (hashlib.sha256(_KLAIM.encode()).hexdigest(), _KLAIM),
    _SID_KEPUTUSAN: (hashlib.sha256(_KEPUTUSAN.encode()).hexdigest(), _KEPUTUSAN),
}
_SKEMA = skema_dengan_amplop(FUNGSI_P04.skema_isi)
_KATA_TERLARANG = {
    "if", "then", "else", "minLength", "maxLength", "minItems", "maxItems", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "pattern",
}  # fmt: skip
_NAMA_TERLARANG = ("approve", "setuju", "skor", "keputusan")


@pytest.fixture(autouse=True)
def _bersihkan_registri():
    FUNGSI_TERDAFTAR.clear()
    yield
    FUNGSI_TERDAFTAR.clear()


def _isi(**ubah: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "material": True,
        "materiality_rationale": "pelatihan tidak tercatat pada materi",
        "one_neutral_question": "Bagaimana pelatihan itu dicatat oleh sekolah?",
        "why_ask": "agar Tim memahami dasar klaim",
        "preferred_role": "Wakil kepala sekolah bidang kurikulum",
        "alternatives": ["periksa daftar hadir pelatihan"],
        "limitations": ["hanya memeriksa materi yang diberikan"],
    }
    d.update(ubah)
    return d


def _amplop(isi: dict[str, Any], **ubah: Any) -> str:
    d: dict[str, Any] = {
        "status": "AI_DRAFT",
        "source_refs": [{"source_id": "s1", "source_hash": "h1"}],
        "cited_spans": [{"source_id": "s1", "span": "jadwal rapat guru"}],
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


# --- skema ---


def test_skema_rekursif_tanpa_kata_terlarang_dan_objek_tertutup():
    for skema in (SKEMA_ISI_P04, _SKEMA):
        for node in _telusuri(skema):
            assert not (_KATA_TERLARANG & node.keys()), node
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
    assert FUNGSI_P04.kode == "P04" and FUNGSI_P04.prompt_version == "p04-1"


def test_tujuh_field_wajib_dan_tanpa_nama_persetujuan_skor_atau_keputusan():
    nama = list(_nama_properti(SKEMA_ISI_P04))
    assert set(SKEMA_ISI_P04["required"]) == {
        "material", "materiality_rationale", "one_neutral_question", "why_ask",
        "preferred_role", "alternatives", "limitations",
    }  # fmt: skip
    for n in nama:
        assert not any(k in n.casefold() for k in _NAMA_TERLARANG), n
    props = SKEMA_ISI_P04["properties"]
    anyof = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    for kunci in ("one_neutral_question", "why_ask", "preferred_role"):
        assert props[kunci] == anyof
    assert props["material"] == {"type": "boolean"}


def test_keluaran_sah_lolos_dan_material_false_dengan_null_juga_lolos():
    assert cek_keluaran(_amplop(_isi()), _SKEMA, _SUMBER).status_qa == "LOLOS"
    tanpa = _isi(material=False, one_neutral_question=None, why_ask=None, preferred_role=None)
    h = cek_keluaran(_amplop(tanpa), _SKEMA, _SUMBER)
    assert (h.status_qa, h.kode) == ("LOLOS", ())


def test_pertanyaan_larik_skema_tidak_sah():
    isi = _isi(one_neutral_question=["satu?", "dua?"])
    h = cek_keluaran(_amplop(isi), _SKEMA, _SUMBER)
    assert (h.status_qa, h.kode) == ("KARANTINA", ("SKEMA_TIDAK_SAH",))


@pytest.mark.parametrize("tambah", ["approve", "setuju", "skor", "keputusan"])
def test_field_persetujuan_atau_keputusan_ditolak_skema(tambah):
    isi = _isi()
    isi[tambah] = True
    assert cek_keluaran(_amplop(isi), _SKEMA, _SUMBER).kode == ("SKEMA_TIDAK_SAH",)


def test_field_wajib_hilang_dan_tipe_salah_skema_tidak_sah():
    isi = _isi()
    del isi["why_ask"]
    assert cek_keluaran(_amplop(isi), _SKEMA, _SUMBER).kode == ("SKEMA_TIDAK_SAH",)
    assert cek_keluaran(_amplop(_isi(material="ya")), _SKEMA, _SUMBER).kode == ("SKEMA_TIDAK_SAH",)


def test_sitasi_ke_sumber_klaim_tervalidasi_dan_span_karangan_dikarantina():
    ok = _amplop(_isi(), cited_spans=[{"source_id": _SID_KLAIM, "span": "pelatihan penyusunan"}])
    assert cek_keluaran(ok, _SKEMA, _SUMBER).status_qa == "LOLOS"
    palsu = _amplop(_isi(), cited_spans=[{"source_id": _SID_KLAIM, "span": "kalimat karangan"}])
    assert cek_keluaran(palsu, _SKEMA, _SUMBER).kode == ("KUTIPAN_TIDAK_DITEMUKAN",)


# --- aturan_p04 ---


@pytest.mark.parametrize(
    ("material", "pertanyaan", "harapan"),
    [
        (True, "Bagaimana pelatihan dicatat?", []),
        (True, None, ["ATURAN_P04_DILANGGAR"]),
        (False, None, []),
        (False, "Bagaimana pelatihan dicatat?", ["ATURAN_P04_DILANGGAR"]),
    ],
)
def test_aturan_empat_kombinasi_material_dan_pertanyaan(material, pertanyaan, harapan):
    assert aturan_p04(_isi(material=material, one_neutral_question=pertanyaan), {}) == harapan


@pytest.mark.parametrize(
    ("material", "pertanyaan", "harapan"),
    [
        (True, "", ["ATURAN_P04_DILANGGAR"]),
        (True, "   \n\t ", ["ATURAN_P04_DILANGGAR"]),
        (False, "", []),
        (False, "   ", []),
    ],
)
def test_aturan_pertanyaan_kosong_dan_hanya_spasi_dianggap_tidak_ada(material, pertanyaan, harapan):
    assert aturan_p04(_isi(material=material, one_neutral_question=pertanyaan), {}) == harapan


def test_aturan_dua_tanda_tanya_lebih_dari_satu_pertanyaan():
    dua = "Siapa yang mencatat? Kapan dicatat?"
    assert aturan_p04(_isi(one_neutral_question=dua), {}) == ["LEBIH_DARI_SATU_PERTANYAAN"]
    # material=false + dua tanda tanya melanggar keduanya.
    assert aturan_p04(_isi(material=False, one_neutral_question=dua), {}) == [
        "ATURAN_P04_DILANGGAR",
        "LEBIH_DARI_SATU_PERTANYAAN",
    ]
    assert aturan_p04(_isi(one_neutral_question="Satu? Dua? Tiga?"), {}) == [
        "LEBIH_DARI_SATU_PERTANYAAN"
    ]


def test_aturan_material_true_tanpa_tanda_tanya_tidak_ditambah_aturan():
    """Perilaku yang dilaporkan, bukan diperbaiki: pertanyaan tanpa tanda tanya lolos."""
    assert aturan_p04(_isi(one_neutral_question="Jelaskan pencatatan pelatihan itu"), {}) == []


def test_aturan_terdaftar_hanya_untuk_p04():
    assert ATURAN_ISI == {"P01": aturan_p01, "P04": aturan_p04}


# --- parameter dan id sumber ---


def test_parameter_sah_dan_menolak_teks_bebas():
    nid = str(uuid.uuid4())
    assert ParameterP04(narasi_id=nid, periode="2026-27").periode == "2026-27"
    assert ParameterP04(narasi_id=nid, periode="2026/27").periode == "2026/27"
    for buruk in ("bukan-uuid", "", nid.upper(), nid + "x"):
        with pytest.raises(ValidationError):
            ParameterP04(narasi_id=buruk, periode="2026-27")
    for buruk in ("2026/27 ganjil", " ", "", "teks bebas tentang murid", "a" * 101):
        with pytest.raises(ValidationError):
            ParameterP04(narasi_id=nid, periode=buruk)
    with pytest.raises(ValidationError):
        ParameterP04(narasi_id=nid, periode="2026-27", klaim="x")  # type: ignore[call-arg]


def test_id_sumber_deterministik_berawalan_dan_tidak_memuat_teks():
    assert id_sumber_klaim(_KLAIM) == id_sumber_klaim(_KLAIM)
    assert id_sumber_klaim(_KLAIM) != id_sumber_klaim(_KLAIM + "!")
    awalan, _, ujung = _SID_KLAIM.partition(":")
    assert awalan == "klaim" and uuid.UUID(ujung).version == 5
    assert _SID_KEPUTUSAN.startswith("keputusan:") and _KEPUTUSAN not in _SID_KEPUTUSAN
    assert id_sumber_klaim("sama") != id_sumber_keputusan("sama")


# --- instruksi dan katalog ---


def test_instruksi_memuat_setiap_larangan_body():
    ins = FUNGSI_P04.instruksi
    assert "Periksa materi yang ada lebih dulu" in ins
    assert "Bila sumber sudah menjawab klaim" in ins and "material dengan false" in ins
    assert "tepat satu pertanyaan netral" in ins
    assert "tanpa mengarahkan jawaban" in ins
    assert "Jangan meminta nama murid atau keluarga" in ins
    assert "Jangan mengisi persetujuan, skor, atau keputusan" in ins
    assert "Anda tidak mengirim apa pun kepada siapa pun" in ins
    assert "bukan nama orang" in ins
    assert "cited_spans" in ins and "bahasa Indonesia" in ins
    assert susun_instruksi(ins).endswith(ins)


def test_katalog_memuat_p04_dan_terdaftar_hanya_bila_disebut():
    assert KATALOG_FUNGSI["P04"] is FUNGSI_P04
    daftarkan_fungsi(Settings(ai_fungsi_aktif=[]))
    assert "P04" not in FUNGSI_TERDAFTAR
    daftarkan_fungsi(Settings(ai_fungsi_aktif=["P04"]))
    assert FUNGSI_TERDAFTAR == {"P04": FUNGSI_P04}


@pytest.mark.parametrize("teks", [_KLAIM, _KEPUTUSAN])
def test_sumber_klaim_dan_keputusan_dengan_email_ditolak_gerbang(teks):
    sid = id_sumber_klaim(teks)
    kotor = f"{teks} Hubungi kontak.fiktif@contoh.example."
    s = SumberAi(
        source_id=sid, source_hash=hashlib.sha256(kotor.encode()).hexdigest(),
        jenis="SINTETIS", teks=kotor,
    )  # fmt: skip
    h = gerbang_masukan(s, [], Settings(_env_file=None, ai_pii_mode="BLOKIR"))
    assert (h.lolos, h.alasan) == (False, "PII_DITEMUKAN")
    bersih = SumberAi(
        source_id=sid, source_hash=hashlib.sha256(teks.encode()).hexdigest(),
        jenis="SINTETIS", teks=teks,
    )  # fmt: skip
    assert gerbang_masukan(bersih, [], Settings(_env_file=None, ai_pii_mode="BLOKIR")).lolos
