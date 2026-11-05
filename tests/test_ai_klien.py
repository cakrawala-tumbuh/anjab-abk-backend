"""Test klien model: bentuk permintaan, pemetaan respons, dan pemetaan galat.

Memakai SDK ``anthropic`` sungguhan di atas transport tiruan (``httpx2.MockTransport``);
tidak ada jaringan dan tidak ada kunci API sungguhan.
"""

from __future__ import annotations

import json
from typing import Any

import anthropic
import httpx2
import pytest

from anjab_abk_backend.ai.klien import (
    AnthropicKlienModel,
    KesalahanModelPermanen,
    KesalahanModelSementara,
    KunciModelTidakAda,
)
from anjab_abk_backend.config import Settings

_SKEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["a"],
    "properties": {"a": {"type": "string"}},
}
_RAHASIA = "RAHASIA-MASUKAN-XYZ"


def _sse(nama: str, data: dict[str, Any]) -> str:
    return f"event: {nama}\ndata: {json.dumps(data)}\n\n"


def _aliran(
    blok: list[dict[str, Any]], *, stop: str = "end_turn", model: str = "claude-opus-5-5"
) -> str:
    out = _sse(
        "message_start",
        {
            "type": "message_start",
            "message": {
                "id": "msg_1", "type": "message", "role": "assistant", "model": model,
                "content": [], "stop_reason": None, "stop_sequence": None,
                "usage": {"input_tokens": 11, "output_tokens": 1},
            },
        },
    )  # fmt: skip
    for i, b in enumerate(blok):
        if b["type"] == "text":
            mulai = {"type": "text", "text": ""}
            delta = {"type": "text_delta", "text": b["text"]}
        else:
            mulai = {"type": "thinking", "thinking": "", "signature": ""}
            delta = {"type": "thinking_delta", "thinking": b["thinking"]}
        out += _sse("content_block_start", {"type": "content_block_start", "index": i,
                                            "content_block": mulai})  # fmt: skip
        out += _sse("content_block_delta", {"type": "content_block_delta", "index": i,
                                            "delta": delta})  # fmt: skip
        out += _sse("content_block_stop", {"type": "content_block_stop", "index": i})
    out += _sse(
        "message_delta",
        {"type": "message_delta", "delta": {"stop_reason": stop, "stop_sequence": None},
         "usage": {"output_tokens": 7}},
    )  # fmt: skip
    return out + _sse("message_stop", {"type": "message_stop"})


class _Transport:
    def __init__(self, respons: httpx2.Response | None = None, galat: Exception | None = None):
        self.respons, self.galat, self.permintaan = respons, galat, None

    def __call__(self, req: httpx2.Request) -> httpx2.Response:
        self.permintaan = req
        if self.galat:
            raise self.galat
        assert self.respons is not None
        return self.respons

    @property
    def badan(self) -> dict[str, Any]:
        return json.loads(self.permintaan.content)


def _ok(blok=None, **kw) -> httpx2.Response:
    blok = blok if blok is not None else [{"type": "text", "text": '{"a":"b"}'}]
    return httpx2.Response(
        200, headers={"content-type": "text/event-stream"}, text=_aliran(blok, **kw)
    )


def _galat(status: int, tipe: str = "api_error") -> httpx2.Response:
    return httpx2.Response(
        status, json={"type": "error", "error": {"type": tipe, "message": _RAHASIA}}
    )


def _klien(
    tr: _Transport, *, model: str = "claude-opus-5-5", effort: str = "high", **setelan: Any
) -> AnthropicKlienModel:
    sdk = anthropic.Anthropic(
        api_key="kunci-palsu", max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(tr)),
    )  # fmt: skip
    return AnthropicKlienModel(
        Settings(_env_file=None, **setelan),
        kunci_api="kunci-palsu", model=model, effort=effort, klien=sdk,
    )  # fmt: skip


def _panggil(k: AnthropicKlienModel):
    return k.panggil("instruksi", _RAHASIA, _SKEMA)


def test_badan_permintaan_sesuai_keputusan_desain():
    tr = _Transport(_ok())
    _panggil(_klien(tr))
    b = tr.badan
    assert b["model"] == "claude-opus-5-5"
    assert b["max_tokens"] == 16000
    assert b["system"] == "instruksi"
    assert b["messages"] == [{"role": "user", "content": _RAHASIA}]
    assert b["thinking"] == {"type": "adaptive"}
    assert b["output_config"] == {
        "effort": "high",
        "format": {"type": "json_schema", "schema": _SKEMA},
    }
    assert b["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in tr.permintaan.headers["anthropic-beta"]
    for dilarang in ("tools", "temperature", "top_p", "top_k", "inference_geo"):
        assert dilarang not in b
    assert b["messages"][-1]["role"] == "user"  # tanpa prefill


def test_fallback_dimatikan_tidak_terkirim():
    tr = _Transport(_ok())
    _panggil(_klien(tr, ai_refusal_fallback=False))
    assert "fallbacks" not in tr.badan
    assert "server-side-fallback" not in tr.permintaan.headers.get("anthropic-beta", "")


def test_inference_geo_terkirim_bila_diisi_dan_tidak_bila_kosong():
    tr = _Transport(_ok())
    _panggil(_klien(tr, ai_inference_geo="us"))
    assert tr.badan["inference_geo"] == "us"
    tr2 = _Transport(_ok())
    _panggil(_klien(tr2, ai_inference_geo=""))
    assert "inference_geo" not in tr2.badan


def test_model_effort_argumen_dan_max_tokens_dipakai():
    tr = _Transport(_ok())
    _panggil(_klien(tr, model="m-x", effort="low", ai_max_tokens=123))
    assert (tr.badan["model"], tr.badan["max_tokens"]) == ("m-x", 123)
    assert tr.badan["output_config"]["effort"] == "low"


def test_end_turn_thinking_diabaikan_teks_dan_token_terisi():
    blok = [{"type": "thinking", "thinking": "mikir"}, {"type": "text", "text": '{"a":"b"}'}]
    j = _panggil(_klien(_Transport(_ok(blok, model="claude-lain"))))
    assert j.teks == '{"a":"b"}'
    assert j.stop_reason == "end_turn"
    assert j.model_dilayani == "claude-lain"  # dari respons, bukan konfigurasi
    assert (j.input_tokens, j.output_tokens) == (11, 7)
    assert "mikir" not in repr(j)


def test_refusal_teks_none_tanpa_galat():
    j = _panggil(_klien(_Transport(_ok([{"type": "text", "text": "maaf"}], stop="refusal"))))
    assert j.teks is None
    assert j.stop_reason == "refusal"


def test_max_tokens_stop_reason_diteruskan():
    j = _panggil(_klien(_Transport(_ok(stop="max_tokens"))))
    assert j.stop_reason == "max_tokens"


@pytest.mark.parametrize("status", [429, 500, 503, 529])
def test_status_sementara(status):
    with pytest.raises(KesalahanModelSementara):
        _panggil(_klien(_Transport(_galat(status))))


def test_timeout_dan_jaringan_sementara():
    req = httpx2.Request("POST", "http://x")
    for exc in (httpx2.ReadTimeout("t", request=req), httpx2.ConnectError("c", request=req)):
        with pytest.raises(KesalahanModelSementara):
            _panggil(_klien(_Transport(galat=exc)))


@pytest.mark.parametrize("status", [400, 401])
def test_status_permanen(status):
    with pytest.raises(KesalahanModelPermanen):
        _panggil(_klien(_Transport(_galat(status, "invalid_request_error"))))


def test_kunci_kosong_klien_sdk_tidak_dibuat_walau_env_terisi(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "kunci-env-sintetis")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "token-env-sintetis")

    def _larang(*_a: Any, **_k: Any) -> None:
        raise AssertionError("klien SDK tidak boleh dibuat")

    monkeypatch.setattr(anthropic, "Anthropic", _larang)
    for kosong in (None, ""):
        with pytest.raises(KunciModelTidakAda):
            AnthropicKlienModel(Settings(_env_file=None), kunci_api=kosong, model="m", effort="low")


def test_klien_sdk_menerima_kunci_eksplisit_bukan_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "kunci-env-sintetis")
    diterima: dict[str, Any] = {}
    asli = anthropic.Anthropic

    def _catat(**kw: Any):
        diterima.update(kw)
        return asli(**kw)

    monkeypatch.setattr(anthropic, "Anthropic", _catat)
    k = AnthropicKlienModel(
        Settings(_env_file=None), kunci_api="kunci-db-sintetis", model="m", effort="low"
    )
    k._dapatkan_klien()
    assert diterima["api_key"] == "kunci-db-sintetis"
    assert diterima["max_retries"] == 0


_KUNCI_PEMANGGIL = "kunci-pemanggil-sintetis"
_ENV_JAHAT_HEADER = "\n".join(
    [
        "X-Jahat: 1",
        "X-Api-Key: kunci-jahat",
        "Authorization: Bearer jahat",
        "anthropic-version: 1999-01-01",
    ]
)


_SDK_ASLI = anthropic.Anthropic


def _bersihkan_env_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    for nama in (
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_CUSTOM_HEADERS",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
    ):
        monkeypatch.delenv(nama, raising=False)


def _pasang_transport(monkeypatch: pytest.MonkeyPatch, tr: _Transport) -> None:
    """Membungkus ``anthropic.Anthropic`` agar hanya menambah ``http_client`` tiruan."""

    def _bungkus(**kw: Any):
        kw["http_client"] = httpx2.Client(transport=httpx2.MockTransport(tr))
        return _SDK_ASLI(**kw)

    monkeypatch.setattr(anthropic, "Anthropic", _bungkus)


def _kirim_lewat_model(monkeypatch: pytest.MonkeyPatch, kali: int = 1) -> httpx2.Request:
    """Memanggil ``AnthropicKlienModel.panggil`` sungguhan; mengembalikan permintaan terakhir."""
    tr = _Transport(_ok())
    _pasang_transport(monkeypatch, tr)
    k = AnthropicKlienModel(
        Settings(_env_file=None), kunci_api=_KUNCI_PEMANGGIL, model="m", effort="low"
    )
    for _ in range(kali):
        tr.respons = _ok()
        k.panggil("instruksi", _RAHASIA, _SKEMA)
    return tr.permintaan


def test_kontrol_sdk_langsung_menuruti_env_jahat(monkeypatch):
    _bersihkan_env_sdk(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://jahat.invalid")
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", _ENV_JAHAT_HEADER)
    tr = _Transport(_ok())
    sdk = anthropic.Anthropic(
        api_key=_KUNCI_PEMANGGIL,
        max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(tr)),
    )
    with sdk.beta.messages.stream(
        model="m", max_tokens=5, messages=[{"role": "user", "content": "x"}]
    ) as aliran:
        aliran.get_final_message()
    assert tr.permintaan.url.host == "jahat.invalid"
    assert tr.permintaan.headers["x-jahat"] == "1"
    assert tr.permintaan.headers["authorization"] == "Bearer jahat"
    assert tr.permintaan.headers["x-api-key"] == "kunci-jahat"


def test_tujuan_dikunci_meski_env_base_url_jahat(monkeypatch):
    _bersihkan_env_sdk(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://jahat.invalid")
    req = _kirim_lewat_model(monkeypatch)
    assert req.url.host == "api.anthropic.com"
    assert req.url.scheme == "https"


def test_header_env_jahat_tidak_terkirim_sama_dengan_tanpa_env(monkeypatch):
    _bersihkan_env_sdk(monkeypatch)
    dasar = _kirim_lewat_model(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", _ENV_JAHAT_HEADER)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "token-env-sintetis")
    for req in (_kirim_lewat_model(monkeypatch), _kirim_lewat_model(monkeypatch, kali=2)):
        assert "x-jahat" not in req.headers
        # SDK 2.5.0 mengirim api_key sebagai ``Authorization: Bearer`` (bukan x-api-key).
        assert req.headers["authorization"] == f"Bearer {_KUNCI_PEMANGGIL}"
        assert req.headers["authorization"] == dasar.headers["authorization"]
        assert "x-api-key" not in req.headers
        assert "x-api-key" not in dasar.headers
        assert req.headers["anthropic-version"] == dasar.headers["anthropic-version"]
        assert req.headers["anthropic-version"] != "1999-01-01"
        assert set(req.headers) == set(dasar.headers)


def test_tanpa_env_tujuan_dan_kunci_pemanggil(monkeypatch):
    _bersihkan_env_sdk(monkeypatch)
    req = _kirim_lewat_model(monkeypatch)
    assert req.url.host == "api.anthropic.com"
    assert req.headers["authorization"] == f"Bearer {_KUNCI_PEMANGGIL}"
    assert "x-api-key" not in req.headers


def test_sdk_tanpa_custom_headers_gagal_tertutup_tanpa_permintaan(monkeypatch):
    _bersihkan_env_sdk(monkeypatch)
    tr = _Transport(_ok())

    def _bungkus(**kw: Any):
        kw["http_client"] = httpx2.Client(transport=httpx2.MockTransport(tr))
        sdk = _SDK_ASLI(**kw)
        del sdk._custom_headers
        return sdk

    monkeypatch.setattr(anthropic, "Anthropic", _bungkus)
    k = AnthropicKlienModel(
        Settings(_env_file=None), kunci_api=_KUNCI_PEMANGGIL, model="m", effort="low"
    )
    with pytest.raises(KesalahanModelPermanen, match="tidak dapat diamankan"):
        k.panggil("instruksi", _RAHASIA, _SKEMA)
    assert tr.permintaan is None


def test_klien_dibuat_malas_bukan_saat_konstruksi(monkeypatch):
    def _larang(**_k: Any) -> None:
        raise AssertionError("klien SDK dibuat saat konstruksi")

    monkeypatch.setattr(anthropic, "Anthropic", _larang)
    AnthropicKlienModel(Settings(_env_file=None), kunci_api="k-sintetis-1", model="m", effort="low")


def test_repr_tidak_memuat_kunci():
    k = AnthropicKlienModel(
        Settings(_env_file=None), kunci_api="KUNCI-RAHASIA-SINTETIS", model="m", effort="low"
    )
    assert "KUNCI-RAHASIA-SINTETIS" not in repr(k)
    assert "m" in repr(k)


@pytest.mark.parametrize("status", [400, 429, 500])
def test_pesan_galat_tidak_memuat_masukan(status):
    with pytest.raises((KesalahanModelPermanen, KesalahanModelSementara)) as e:
        _panggil(_klien(_Transport(_galat(status))))
    assert _RAHASIA not in str(e.value)
    assert e.value.__cause__ is None
