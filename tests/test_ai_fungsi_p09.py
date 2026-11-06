"""Test fungsi AI P09 (kritik AI atas versi narasi): skema, instruksi, parameter, katalog."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from anjab_abk_backend.ai.fungsi_p09 import (
    FUNGSI_P09,
    KATEGORI_TEMUAN_P09,
    SKEMA_ISI_P09,
    ParameterP09,
    id_sumber_versi,
)
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.guardrail import susun_instruksi
from anjab_abk_backend.ai.katalog import KATALOG_FUNGSI, daftarkan_fungsi
from anjab_abk_backend.ai.keluaran import cek_keluaran, skema_dengan_amplop
from anjab_abk_backend.ai.masukan import peta_sumber
from anjab_abk_backend.ai.redaksi import SumberAi, gerbang_masukan
from anjab_abk_backend.config import Settings

_VID = str(uuid.uuid4())
_DRAF = "Guru menyusun perangkat ajar dan seluruh siswa tuntas."
_SID = id_sumber_versi(_VID)
_SUMBER = {
    "s1": ("h1", "Guru menyusun perangkat ajar pada awal semester."),
    _SID: (hashlib.sha256(_DRAF.encode()).hexdigest(), _DRAF),
}
_SKEMA = skema_dengan_amplop(FUNGSI_P09.skema_isi)
# Kata kunci yang tidak boleh ada di skema keluaran (aturan #87 dan skema P10).
_KATA_TERLARANG = {
    "if", "then", "else", "minLength", "maxLength", "minItems", "maxItems", "minimum",
    "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf", "pattern",
}  # fmt: skip
_NAMA_TERLARANG = ("approve", "setuju", "skor")


@pytest.fixture(autouse=True)
def _bersihkan_registri():
    FUNGSI_TERDAFTAR.clear()
    yield
    FUNGSI_TERDAFTAR.clear()


def _isi(**ubah: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "peran": "REVIEWER_OTOMATIS_PEMBANTU",
        "blocking_findings": [
            {
                "temuan": "klaim tanpa dasar",
                "kategori": "KLAIM_TANPA_DASAR",
                "source_id": "s1",
                "span": "menyusun perangkat ajar",
            }
        ],
        "major_findings": [],
        "correction_proposals": [
            {"span": "seluruh siswa tuntas", "usulan": "hapus klaim", "alasan": "tak ada dasar"}
        ],
        "limitations": ["tidak memeriksa makna parafrasa"],
    }
    d.update(ubah)
    return d


def _amplop(isi: dict[str, Any], **ubah: Any) -> str:
    d: dict[str, Any] = {
        "status": "AI_DRAFT",
        "source_refs": [{"source_id": "s1", "source_hash": "h1"}],
        "cited_spans": [{"source_id": _SID, "span": "seluruh siswa tuntas"}],
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
    """Semua nama field pada kedalaman mana pun (kunci di bawah ``properties``)."""
    for node in _telusuri(skema):
        props = node.get("properties")
        if isinstance(props, dict):
            yield from props


def test_skema_rekursif_tanpa_kata_terlarang_dan_objek_tertutup():
    for skema in (SKEMA_ISI_P09, _SKEMA):
        for node in _telusuri(skema):
            assert not (_KATA_TERLARANG & node.keys()), node
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
    assert FUNGSI_P09.kode == "P09" and FUNGSI_P09.prompt_version == "p09-1"


def test_nama_field_tanpa_persetujuan_skor_atau_keputusan_pada_semua_kedalaman():
    nama = list(_nama_properti(SKEMA_ISI_P09))
    # temuan dan correction_proposals bersarang: pastikan penelusuran memang menjangkaunya.
    assert {"peran", "blocking_findings", "temuan", "kategori", "usulan", "alasan"} <= set(nama)
    for n in nama:
        assert not any(k in n.casefold() for k in _NAMA_TERLARANG), n
    assert "keputusan" not in " ".join(nama).casefold()


def test_telusur_nama_menangkap_pelanggaran_bersarang():
    """Penjaga penjaga: field terlarang di kedalaman ketiga tertangkap oleh penelusur."""
    skema = {
        "type": "object",
        "properties": {
            "a": {"type": "array", "items": {"type": "object", "properties": {"skor_akhir": {}}}}
        },
    }
    assert "skor_akhir" in set(_nama_properti(skema))


def test_peran_const_dan_enum_kategori():
    assert SKEMA_ISI_P09["properties"]["peran"] == {
        "type": "string",
        "const": "REVIEWER_OTOMATIS_PEMBANTU",
    }
    item = SKEMA_ISI_P09["properties"]["blocking_findings"]["items"]
    assert item["properties"]["kategori"]["enum"] == list(KATEGORI_TEMUAN_P09)
    assert set(KATEGORI_TEMUAN_P09) == {
        "KLAIM_TANPA_DASAR", "ASUMSI_TERSEMBUNYI", "BIAS_PROMPT", "PRIVASI",
        "SALAH_TAUTAN", "PENGHILANGAN", "KONFLIK_METODE",
    }  # fmt: skip


def test_keluaran_sah_lolos_dan_sitasi_ke_draf_tervalidasi():
    h = cek_keluaran(_amplop(_isi()), _SKEMA, _SUMBER)
    assert (h.status_qa, h.kode) == ("LOLOS", ())


def test_sitasi_ke_draf_dengan_span_yang_tidak_ada_dikarantina():
    teks = _amplop(_isi(), cited_spans=[{"source_id": _SID, "span": "kalimat karangan model"}])
    h = cek_keluaran(teks, _SKEMA, _SUMBER)
    assert (h.status_qa, h.kode) == ("KARANTINA", ("KUTIPAN_TIDAK_DITEMUKAN",))


def test_sumber_draf_fiktif_dikarantina():
    teks = _amplop(_isi(), cited_spans=[{"source_id": f"versi:{uuid.uuid4()}", "span": "x"}])
    assert cek_keluaran(teks, _SKEMA, _SUMBER).kode == ("SUMBER_FIKTIF",)


def test_peran_lain_skema_tidak_sah():
    h = cek_keluaran(_amplop(_isi(peran="PENYETUJU")), _SKEMA, _SUMBER)
    assert (h.status_qa, h.kode) == ("KARANTINA", ("SKEMA_TIDAK_SAH",))


def test_kategori_di_luar_enum_skema_tidak_sah():
    isi = _isi(major_findings=[{"temuan": "x", "kategori": "LAIN", "source_id": "s1", "span": "x"}])
    assert cek_keluaran(_amplop(isi), _SKEMA, _SUMBER).kode == ("SKEMA_TIDAK_SAH",)


@pytest.mark.parametrize("tambah", ["approve", "setuju", "skor"])
def test_field_persetujuan_ditolak_skema(tambah):
    isi = _isi()
    isi[tambah] = True
    assert cek_keluaran(_amplop(isi), _SKEMA, _SUMBER).kode == ("SKEMA_TIDAK_SAH",)


def test_tanpa_cited_spans_dikarantina_tanpa_sitasi():
    h = cek_keluaran(_amplop(_isi(), cited_spans=[]), _SKEMA, _SUMBER)
    assert (h.status_qa, h.kode) == ("KARANTINA", ("TANPA_SITASI",))


def test_tanpa_temuan_tetap_lolos_bila_ada_sitasi():
    isi = _isi(blocking_findings=[], major_findings=[], correction_proposals=[])
    assert cek_keluaran(_amplop(isi), _SKEMA, _SUMBER).status_qa == "LOLOS"


def test_parameter_sah_dan_menolak_teks_bebas():
    assert ParameterP09(narasi_versi_id=_VID).narasi_versi_id == _VID
    for buruk in ("bukan-uuid", "", "teks bebas tentang murid", _VID.upper(), _VID + "x"):
        with pytest.raises(ValidationError):
            ParameterP09(narasi_versi_id=buruk)
    with pytest.raises(ValidationError):
        ParameterP09(narasi_versi_id=_VID, lain="x")  # type: ignore[call-arg]


def test_instruksi_memuat_setiap_larangan_body():
    ins = FUNGSI_P09.instruksi
    assert "Jangan menyetujui draf" in ins
    assert "hanya atas draf dan sumber yang diberikan" in ins
    assert "Kemiripan bukan bukti" in ins
    assert "skor WCP atau DCS sah" in ins
    assert "Dua persetujuan bukan dua bukti independen" in ins
    assert "menghapus atau menyarankan penghapusan kontrol wajib" in ins
    assert "wajib mengutip minimal satu span" in ins and "cited_spans" in ins
    assert "REVIEWER_OTOMATIS_PEMBANTU" in ins
    assert susun_instruksi(ins).endswith(ins)


def test_katalog_memuat_p09_dan_terdaftar_hanya_bila_disebut():
    assert KATALOG_FUNGSI["P09"] is FUNGSI_P09
    daftarkan_fungsi(Settings(ai_fungsi_aktif=[]))
    assert "P09" not in FUNGSI_TERDAFTAR
    daftarkan_fungsi(Settings(ai_fungsi_aktif=["P09"]))
    assert FUNGSI_TERDAFTAR == {"P09": FUNGSI_P09}


def test_source_id_versi_lolos_gerbang_peta_dan_cek_keluaran():
    s = SumberAi(source_id=_SID, source_hash=_SUMBER[_SID][0], jenis="SINTETIS", teks=_DRAF)
    h = gerbang_masukan(s, [], Settings(_env_file=None, ai_pii_mode="BLOKIR"))
    assert h.lolos and h.sumber is not None and h.sumber.source_id == _SID
    peta = peta_sumber([{"source_id": _SID, "source_hash": s.source_hash, "teks": _DRAF}])
    assert peta == {_SID: (s.source_hash, _DRAF)}


def test_draf_dengan_email_ditolak_gerbang():
    teks = "Hubungi kontak.fiktif@contoh.example untuk rincian."
    s = SumberAi(
        source_id=_SID,
        source_hash=hashlib.sha256(teks.encode()).hexdigest(),
        jenis="SINTETIS",
        teks=teks,
    )
    h = gerbang_masukan(s, [], Settings(_env_file=None, ai_pii_mode="BLOKIR"))
    assert (h.lolos, h.alasan) == (False, "PII_DITEMUKAN")
