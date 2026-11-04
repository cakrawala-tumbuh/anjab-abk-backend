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


def _klien(tr: _Transport, **setelan: Any) -> AnthropicKlienModel:
    sdk = anthropic.Anthropic(
        api_key="kunci-palsu", max_retries=0,
        http_client=httpx2.Client(transport=httpx2.MockTransport(tr)),
    )  # fmt: skip
    return AnthropicKlienModel(Settings(**setelan), klien=sdk)


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


def test_env_model_effort_max_tokens_dipakai():
    tr = _Transport(_ok())
    _panggil(_klien(tr, ai_model="m-x", ai_effort="low", ai_max_tokens=123))
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


def test_kunci_tidak_ada(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(KunciModelTidakAda):
        _panggil(AnthropicKlienModel(Settings()))


def test_klien_dibuat_malas_bukan_saat_impor(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    AnthropicKlienModel(Settings())  # konstruksi tanpa kunci tidak melempar


@pytest.mark.parametrize("status", [400, 429, 500])
def test_pesan_galat_tidak_memuat_masukan(status):
    with pytest.raises((KesalahanModelPermanen, KesalahanModelSementara)) as e:
        _panggil(_klien(_Transport(_galat(status))))
    assert _RAHASIA not in str(e.value)
    assert e.value.__cause__ is None
