"""Test fungsi AI P10 dan pendaftaran fungsi lewat ``AI_FUNGSI_AKTIF``."""

from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import ValidationError

from anjab_abk_backend.ai.fungsi_p10 import FUNGSI_P10, ParameterP10
from anjab_abk_backend.ai.gateway import FUNGSI_TERDAFTAR
from anjab_abk_backend.ai.guardrail import susun_instruksi
from anjab_abk_backend.ai.katalog import KATALOG_FUNGSI, daftarkan_fungsi
from anjab_abk_backend.ai.keluaran import cek_keluaran, skema_dengan_amplop
from anjab_abk_backend.config import Settings
from anjab_abk_backend.main import create_app

_SUMBER = {"s1": ("h1", "Guru menyusun perangkat ajar setiap semester.")}
_SKEMA = skema_dengan_amplop(FUNGSI_P10.skema_isi)
_KATA_TERLARANG = {"if", "then", "minLength", "minItems"}


@pytest.fixture(autouse=True)
def _bersihkan_registri():
    FUNGSI_TERDAFTAR.clear()
    yield
    FUNGSI_TERDAFTAR.clear()


def _settings(aktif: list[str]) -> Settings:
    return Settings(ai_fungsi_aktif=aktif)


def _isi(**ubah: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "narrative_kind": "F1_FORMAL",
        "draft_text": "Guru menyusun perangkat ajar.",
        "claim_to_source_map": [
            {"claim": "klaim", "source_id": "s1", "span": "menyusun perangkat ajar"}
        ],
        "missing_facts": [],
        "recommended_review_scope": "seluruh draf",
        "label_dokumenter": "DOCUMENTARY_CANDIDATE",
    }
    d.update(ubah)
    return d


def _amplop(isi: dict[str, Any], **ubah: Any) -> str:
    d: dict[str, Any] = {
        "status": "AI_DRAFT",
        "source_refs": [{"source_id": "s1", "source_hash": "h1"}],
        "cited_spans": [{"source_id": "s1", "span": "menyusun perangkat ajar"}],
        "confidence_reason": "kutipan langsung",
        "unknowns": [],
        "contradictions": [],
        "human_review_required": True,
        "isi": isi,
    }
    d.update(ubah)
    return json.dumps(d)


def test_bawaan_kosong_setelah_create_app():
    create_app(settings=_settings([]))
    assert FUNGSI_TERDAFTAR == {}


def test_daftar_p10_idempoten_dan_dikosongkan():
    daftarkan_fungsi(_settings(["P10"]))
    daftarkan_fungsi(_settings(["P10"]))
    assert FUNGSI_TERDAFTAR == {"P10": FUNGSI_P10}
    assert KATALOG_FUNGSI["P10"] is FUNGSI_P10
    assert set(KATALOG_FUNGSI) == {"P01", "P04", "P09", "P10"}
    daftarkan_fungsi(_settings([]))
    assert FUNGSI_TERDAFTAR == {}


def test_create_app_mendaftarkan_dari_env():
    create_app(settings=_settings(["P10"]))
    assert list(FUNGSI_TERDAFTAR) == ["P10"]


def test_kode_tak_dikenal_valueerror_saat_mulai():
    with pytest.raises(ValueError, match="P99"):
        daftarkan_fungsi(_settings(["P99"]))
    with pytest.raises(ValueError):
        create_app(settings=_settings(["P99"]))
    assert FUNGSI_TERDAFTAR == {}


def test_env_json_dibaca(monkeypatch):
    monkeypatch.setenv("AI_FUNGSI_AKTIF", '["P10"]')
    assert Settings().ai_fungsi_aktif == ["P10"]


def _telusuri(skema: Any):
    if isinstance(skema, dict):
        yield skema
        for v in skema.values():
            yield from _telusuri(v)
    elif isinstance(skema, list):
        for v in skema:
            yield from _telusuri(v)


def test_skema_rekursif_tanpa_kata_terlarang_dan_objek_tertutup():
    for node in _telusuri(FUNGSI_P10.skema_isi):
        assert not (_KATA_TERLARANG & node.keys())
    for node in _telusuri(FUNGSI_P10.skema_isi):
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
    for node in _telusuri(_SKEMA):
        assert not (_KATA_TERLARANG & node.keys())
    assert FUNGSI_P10.kode == "P10" and FUNGSI_P10.prompt_version == "p10-1"


def test_ai_draft_sah_lolos():
    h = cek_keluaran(_amplop(_isi()), _SKEMA, _SUMBER)
    assert (h.status_qa, h.kode) == ("LOLOS", ())


def test_evidence_gap_draft_null():
    teks = _amplop(
        _isi(draft_text=None, claim_to_source_map=[], missing_facts=["volume"]),
        status="EVIDENCE_GAP",
        cited_spans=[],
        unknowns=["volume pekerjaan"],
    )
    h = cek_keluaran(teks, _SKEMA, _SUMBER)
    assert h.status_qa == "EVIDENCE_GAP"


def test_narrative_kind_f2_ditolak_skema():
    h = cek_keluaran(_amplop(_isi(narrative_kind="F2_ACTUAL")), _SKEMA, _SUMBER)
    assert (h.status_qa, h.kode) == ("KARANTINA", ("SKEMA_TIDAK_SAH",))


def test_parameter_sah():
    p = ParameterP10(
        narrative_kind="F1_FORMAL", instrument_id="ti-1", field_key="a.b:c_d", periode="2026-11"
    )
    assert p.periode == "2026-11"


def test_parameter_periode_garis_miring_sah_tapi_spasi_dan_instrument_id_tidak():
    dasar = {"narrative_kind": "F1_FORMAL", "instrument_id": "i", "field_key": "f"}
    assert ParameterP10(**dasar, periode="2026/27").periode == "2026/27"
    with pytest.raises(ValidationError):
        ParameterP10(**dasar, periode="2026/27 ganjil")
    with pytest.raises(ValidationError):
        ParameterP10(**{**dasar, "instrument_id": "a/b"}, periode="2026/27")


@pytest.mark.parametrize(
    "ubah",
    [
        {"instrument_id": "ada spasi"},
        {"field_key": "teks bebas tentang murid"},
        {"periode": ""},
        {"narrative_kind": "F2_ACTUAL"},
        {"lain": "x"},
    ],
)
def test_parameter_menolak_teks_bebas(ubah):
    dasar = {"narrative_kind": "F1_FORMAL", "instrument_id": "i", "field_key": "f", "periode": "p"}
    dasar.update(ubah)
    with pytest.raises(ValidationError):
        ParameterP10(**dasar)


def test_instruksi_memuat_kata_kunci():
    for kata in ("EVIDENCE_GAP", "DOCUMENTARY_CANDIDATE", "draft_text=null", "claim_to_source_map"):
        assert kata in FUNGSI_P10.instruksi
    assert susun_instruksi(FUNGSI_P10.instruksi).endswith(FUNGSI_P10.instruksi)
