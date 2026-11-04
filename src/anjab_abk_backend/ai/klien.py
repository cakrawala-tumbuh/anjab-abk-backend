"""Klien model bahasa (Claude) dengan structured output, tanpa alat.

Satu seam, ``KlienModel``, memisahkan pemanggil dari SDK ``anthropic`` sehingga
uji tidak butuh jaringan atau kunci API. ``AnthropicKlienModel`` adalah
implementasi nyatanya: sinkron, tanpa ``tools``, tanpa parameter sampling, dan
tanpa retry (retry milik job pemanggil). Galat SDK dipetakan ke tiga tipe
internal; pesan galat tidak pernah memuat masukan atau isi respons.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from ..config import Settings

__all__ = [
    "AnthropicKlienModel",
    "JawabanModel",
    "KesalahanModel",
    "KesalahanModelPermanen",
    "KesalahanModelSementara",
    "KlienModel",
    "KunciModelTidakAda",
]

logger = logging.getLogger(__name__)

_BETA_FALLBACK = "server-side-fallback-2026-07-01"

_GALAT_SEMENTARA = (
    anthropic.RateLimitError,
    anthropic.InternalServerError,
    anthropic.ServiceUnavailableError,
    anthropic.OverloadedError,
    anthropic.DeadlineExceededError,
    anthropic.APIConnectionError,  # termasuk APITimeoutError
)


class KesalahanModel(Exception):
    """Akar semua galat klien model."""


class KesalahanModelSementara(KesalahanModel):
    """Galat yang layak diulang pemanggil (rate limit, 5xx, timeout, jaringan)."""


class KesalahanModelPermanen(KesalahanModel):
    """Galat yang tidak akan sembuh dengan mengulang (mis. 400, 401)."""


class KunciModelTidakAda(KesalahanModel):
    """Kunci API (``ANTHROPIC_API_KEY``) tidak tersedia di lingkungan."""


@dataclass(frozen=True)
class JawabanModel:
    """Hasil satu panggilan model.

    Attributes:
        teks: Isi blok ``text`` pertama; ``None`` bila ``stop_reason`` adalah
            ``refusal`` atau tidak ada blok ``text``.
        model_dilayani: Model yang benar-benar melayani (dari ``response.model``,
            bisa berbeda dari konfigurasi bila fallback terjadi).
        stop_reason: ``stop_reason`` respons apa adanya (mis. ``end_turn``,
            ``max_tokens``, ``refusal``).
        input_tokens: Token masukan yang dilaporkan respons.
        output_tokens: Token keluaran yang dilaporkan respons.
    """

    teks: str | None
    model_dilayani: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int


class KlienModel(Protocol):
    """Seam pemanggilan model; diganti tiruan di uji."""

    def panggil(self, instruksi: str, masukan_json: str, skema: dict[str, Any]) -> JawabanModel:
        """Mengirim satu permintaan dan mengembalikan jawabannya.

        Args:
            instruksi: Prompt sistem.
            masukan_json: Masukan (sudah berupa string JSON) sebagai pesan pengguna.
            skema: JSON Schema keluaran terstruktur.

        Returns:
            ``JawabanModel``.

        Raises:
            KesalahanModelSementara: Galat yang layak diulang.
            KesalahanModelPermanen: Galat yang tidak layak diulang.
            KunciModelTidakAda: Kunci API tidak tersedia.
        """
        ...


class AnthropicKlienModel:
    """``KlienModel`` berbasis SDK ``anthropic`` (beta messages, streaming).

    Klien SDK dibuat saat pertama dipakai, bukan saat impor. Kunci hanya dibaca
    SDK dari ``ANTHROPIC_API_KEY``; tidak disimpan di ``Settings``.
    """

    def __init__(self, settings: Settings | None = None, *, klien: Any | None = None) -> None:
        """Menyiapkan klien tanpa membuka koneksi.

        Args:
            settings: Pengaturan; bawaan ``Settings()``.
            klien: Klien SDK siap pakai (untuk uji). Bila diberikan, pemeriksaan
                kunci dilewati.
        """
        self._s = settings or Settings()
        self._klien = klien

    def _dapatkan_klien(self) -> Any:
        """Membuat klien SDK pada pemakaian pertama.

        Raises:
            KunciModelTidakAda: ``ANTHROPIC_API_KEY`` kosong atau SDK menolak kredensial.
        """
        if self._klien is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise KunciModelTidakAda("ANTHROPIC_API_KEY tidak diset.")
            try:
                self._klien = anthropic.Anthropic(
                    timeout=float(self._s.ai_timeout_detik), max_retries=0
                )
            except anthropic.AnthropicError as exc:
                raise KunciModelTidakAda("Klien Anthropic tidak dapat dibuat.") from exc
        return self._klien

    def _argumen(self, instruksi: str, masukan_json: str, skema: dict[str, Any]) -> dict[str, Any]:
        """Menyusun argumen ``messages.stream`` sesuai kebijakan (tanpa alat/sampling)."""
        s = self._s
        arg: dict[str, Any] = {
            "model": s.ai_model,
            "max_tokens": s.ai_max_tokens,
            "system": instruksi,
            "messages": [{"role": "user", "content": masukan_json}],
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": s.ai_effort,
                "format": {"type": "json_schema", "schema": skema},
            },
        }
        if s.ai_refusal_fallback:
            arg["fallbacks"] = "default"
            arg["betas"] = [_BETA_FALLBACK]
        if s.ai_inference_geo:
            arg["inference_geo"] = s.ai_inference_geo
        return arg

    def panggil(self, instruksi: str, masukan_json: str, skema: dict[str, Any]) -> JawabanModel:
        """Memanggil Claude dan memetakan hasil/galat ke tipe internal.

        ``stop_reason`` diperiksa sebelum ``content``: pada ``refusal``, ``teks``
        adalah ``None``. Blok selain ``text`` (``thinking``, ``fallback``) diabaikan
        dan tidak disimpan.

        Raises:
            KesalahanModelSementara: 429/5xx/529, timeout, atau galat jaringan.
            KesalahanModelPermanen: Galat status API lain (mis. 400, 401).
            KunciModelTidakAda: Kunci API tidak tersedia.
        """
        klien = self._dapatkan_klien()
        try:
            with klien.beta.messages.stream(
                **self._argumen(instruksi, masukan_json, skema)
            ) as aliran:
                resp = aliran.get_final_message()
        except _GALAT_SEMENTARA as exc:
            logger.warning("model_galat_sementara", extra={"jenis": type(exc).__name__})
            raise KesalahanModelSementara(_pesan(exc)) from None
        except anthropic.APIStatusError as exc:
            logger.warning("model_galat_permanen", extra={"jenis": type(exc).__name__})
            raise KesalahanModelPermanen(_pesan(exc)) from None
        except anthropic.AnthropicError as exc:
            raise KunciModelTidakAda(f"Kredensial model ditolak ({type(exc).__name__}).") from None

        teks: str | None = None
        if resp.stop_reason != "refusal":
            teks = next((b.text for b in resp.content if b.type == "text"), None)
        return JawabanModel(
            teks=teks,
            model_dilayani=resp.model,
            stop_reason=resp.stop_reason,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )


def _pesan(exc: Exception) -> str:
    """Pesan galat aman: jenis dan status saja, tanpa isi masukan atau respons."""
    status = getattr(exc, "status_code", None)
    return f"{type(exc).__name__}" + (f" (status {status})" if status else "")
