"""Test pemeriksa keluaran model: amplop skema dan kebenaran sitasi."""

from __future__ import annotations

import copy
import json
from typing import Any

from anjab_abk_backend.ai.keluaran import cek_keluaran, skema_dengan_amplop

_ISI = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ringkasan"],
    "properties": {"ringkasan": {"type": "string"}},
}
_SKEMA = skema_dengan_amplop(_ISI)
_SUMBER = {
    "s1": ("h1", "Guru   menyusun\nperangkat ajar setiap semester."),
    "s2": ("h2", "Kepala sekolah menandatangani rapor."),
}
_TERLARANG = {
    "minLength", "maxLength", "minimum", "maximum", "exclusiveMinimum",
    "exclusiveMaximum", "minItems", "maxItems", "pattern", "multipleOf",
}  # fmt: skip


def _ok(**ubah: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "status": "AI_DRAFT",
        "source_refs": [{"source_id": "s1", "source_hash": "h1"}],
        "cited_spans": [{"source_id": "s1", "span": "menyusun perangkat ajar"}],
        "confidence_reason": "kutipan langsung",
        "unknowns": [],
        "contradictions": [],
        "human_review_required": True,
        "isi": {"ringkasan": "x"},
    }
    d.update(ubah)
    return d


def _cek(d: Any):
    return cek_keluaran(d if isinstance(d, str) else json.dumps(d), _SKEMA, _SUMBER)


def test_ai_draft_sah_lolos():
    h = _cek(_ok())
    assert (h.status_qa, h.kode) == ("LOLOS", ())
    assert h.keluaran["isi"] == {"ringkasan": "x"}


def test_evidence_gap_dengan_unknowns():
    h = _cek(_ok(status="EVIDENCE_GAP", cited_spans=[], unknowns=["tidak ada data"]))
    assert (h.status_qa, h.kode) == ("EVIDENCE_GAP", ())


def test_bukan_json():
    h = _cek("bukan json {")
    assert (h.status_qa, h.kode, h.keluaran) == ("KARANTINA", ("JSON_TIDAK_SAH",), None)


def test_field_tambahan_skema_tidak_sah():
    h = _cek({**_ok(), "skor_keyakinan": 0.9})
    assert (h.status_qa, h.kode) == ("KARANTINA", ("SKEMA_TIDAK_SAH",))


def test_review_manusia_false_skema_tidak_sah():
    assert _cek(_ok(human_review_required=False)).kode == ("SKEMA_TIDAK_SAH",)


def test_sumber_fiktif():
    h = _cek(_ok(source_refs=[{"source_id": "zzz", "source_hash": "h"}]))
    assert h.status_qa == "KARANTINA" and h.kode == ("SUMBER_FIKTIF",)


def test_hash_berbeda():
    h = _cek(_ok(source_refs=[{"source_id": "s1", "source_hash": "salah"}]))
    assert h.kode == ("HASH_TIDAK_COCOK",)


def test_kutipan_dari_sumber_lain():
    h = _cek(_ok(cited_spans=[{"source_id": "s1", "span": "menandatangani rapor"}]))
    assert h.kode == ("KUTIPAN_TIDAK_DITEMUKAN",)


def test_kutipan_peka_besar_kecil():
    h = _cek(_ok(cited_spans=[{"source_id": "s1", "span": "GURU menyusun"}]))
    assert h.kode == ("KUTIPAN_TIDAK_DITEMUKAN",)


def test_kutipan_kosong():
    h = _cek(_ok(cited_spans=[{"source_id": "s1", "span": "  "}]))
    assert h.kode == ("KUTIPAN_KOSONG",)


def test_ai_draft_tanpa_sitasi_dan_pelanggaran_ganda():
    assert _cek(_ok(cited_spans=[])).kode == ("TANPA_SITASI",)
    h = _cek(
        _ok(
            source_refs=[{"source_id": "s1", "source_hash": "salah"}],
            cited_spans=[{"source_id": "s2", "span": "tidak ada"}],
        )
    )
    assert h.kode == ("HASH_TIDAK_COCOK", "KUTIPAN_TIDAK_DITEMUKAN")


def test_gap_tanpa_alasan():
    h = _cek(_ok(status="EVIDENCE_GAP", cited_spans=[], unknowns=[]))
    assert h.kode == ("GAP_TANPA_ALASAN",)


def test_skema_rekursif_tertutup_dan_tanpa_kata_kunci_terlarang():
    jumlah_objek = 0

    def jalan(n: Any) -> None:
        nonlocal jumlah_objek
        if isinstance(n, dict):
            assert not (_TERLARANG & set(n)), n
            if n.get("type") == "object":
                jumlah_objek += 1
                assert n["additionalProperties"] is False
                assert set(n["required"]) == set(n["properties"])
            for v in n.values():
                jalan(v)
        elif isinstance(n, list):
            for v in n:
                jalan(v)

    jalan(_SKEMA)
    assert jumlah_objek == 4  # amplop, source_refs, cited_spans, isi


def test_skema_isi_tidak_diubah():
    asli = copy.deepcopy(_ISI)
    skema_dengan_amplop(_ISI)
    assert _ISI == asli
