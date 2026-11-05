"""Klien model bahasa (Claude) dengan structured output, tanpa alat.

Satu seam, ``KlienModel``, memisahkan pemanggil dari SDK ``anthropic`` sehingga
uji tidak butuh jaringan atau kunci API. ``AnthropicKlienModel`` adalah
implementasi nyatanya: sinkron, tanpa ``tools``, tanpa parameter sampling, dan
tanpa retry (retry milik job pemanggil). Galat SDK dipetakan ke tiga tipe
internal; pesan galat tidak pernah memuat masukan atau isi respons.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from ..config import Settings
from .langganan_cli import baca_status_cli, env_claude_p

__all__ = [
    "AnthropicKlienModel",
    "BinaryClaudeTidakAda",
    "ClaudeCliKlienModel",
    "JawabanModel",
    "KesalahanModel",
    "KesalahanModelPermanen",
    "KesalahanModelSementara",
    "KlienModel",
    "KunciModelTidakAda",
    "LanggananBelumMasuk",
]

logger = logging.getLogger(__name__)

_BETA_FALLBACK = "server-side-fallback-2026-07-01"
_BASE_URL_ANTHROPIC = "https://api.anthropic.com"

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
    """Kunci API penyedia tidak tersedia (belum dipasang, tak terbaca, atau ditolak SDK)."""


class BinaryClaudeTidakAda(KesalahanModel):
    """Binary ``claude`` tidak ditemukan saat panggilan (kode ``PENYEDIA_TIDAK_TERSEDIA``)."""


class LanggananBelumMasuk(KesalahanModel):
    """CLI belum masuk ke akun langganan (kode ``LANGGANAN_BELUM_MASUK``)."""


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

    Kunci, model, dan effort diberikan pemanggil (dari pengaturan penyedia di basis
    data); kelas ini tidak membaca ``os.environ`` dan tidak mencatat kunci di mana pun.
    Klien SDK dibuat saat pertama dipakai, bukan saat impor, dengan ``api_key`` eksplisit
    sehingga SDK tidak jatuh ke ``ANTHROPIC_API_KEY`` atau ``ANTHROPIC_AUTH_TOKEN``.
    ``api_key`` eksplisit TIDAK menutup env tujuan dan header: tujuan dikunci ke
    ``_BASE_URL_ANTHROPIC`` dan header dari ``ANTHROPIC_CUSTOM_HEADERS`` dibuang
    (lihat ``_dapatkan_klien``). Versi SDK dipin di ``pyproject.toml``.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        kunci_api: str | None,
        model: str,
        effort: str,
        klien: Any | None = None,
    ) -> None:
        """Menyiapkan klien tanpa membuka koneksi.

        Args:
            settings: Pengaturan (``ai_max_tokens``, timeout, geo, fallback).
            kunci_api: Kunci API teks asli.
            model: Nama model yang diminta.
            effort: Kedalaman berpikir.
            klien: Klien SDK siap pakai (untuk uji). Bila diberikan, ``kunci_api``
                boleh ``None``.

        Raises:
            KunciModelTidakAda: ``kunci_api`` kosong dan ``klien`` tidak diberikan;
                klien SDK tidak pernah dibuat.
        """
        if klien is None and not kunci_api:
            raise KunciModelTidakAda("Kunci API model belum tersedia.")
        self._s = settings
        self._kunci = kunci_api
        self._model = model
        self._effort = effort
        self._klien = klien

    def __repr__(self) -> str:
        """Representasi tanpa kunci."""
        return f"AnthropicKlienModel(model={self._model!r}, effort={self._effort!r})"

    def _dapatkan_klien(self) -> Any:
        """Membuat klien SDK pada pemakaian pertama, dengan tujuan dan header terkunci.

        ``api_key`` eksplisit hanya menutup env kredensial. SDK tetap membaca
        ``ANTHROPIC_BASE_URL`` bila ``base_url`` kosong dan selalu menggabungkan
        ``ANTHROPIC_CUSTOM_HEADERS`` ke header bawaan (paling akhir, sehingga dapat
        menimpa header kredensial). Karena itu ``base_url`` selalu diisi dengan
        ``_BASE_URL_ANTHROPIC`` dan ``_custom_headers`` (satu-satunya tempat hasil env
        tersimpan) dikosongkan segera setelah konstruksi. Klien tidak pernah diturunkan
        lewat ``with_options``/``copy`` karena konstruktor akan membaca env lagi.

        Returns:
            Klien SDK yang di-cache untuk pemanggilan berikutnya.

        Raises:
            KunciModelTidakAda: SDK menolak kredensial.
            KesalahanModelPermanen: Klien SDK tidak punya ``_custom_headers`` (SDK
                berubah); gagal tertutup, tidak ada permintaan yang dikirim.
        """
        if self._klien is None:
            try:
                sdk = anthropic.Anthropic(
                    api_key=self._kunci,
                    base_url=_BASE_URL_ANTHROPIC,
                    timeout=float(self._s.ai_timeout_detik),
                    max_retries=0,
                )
            except anthropic.AnthropicError:
                raise KunciModelTidakAda("Klien Anthropic tidak dapat dibuat.") from None
            if not hasattr(sdk, "_custom_headers"):
                raise KesalahanModelPermanen("Klien SDK tidak dapat diamankan.")
            sdk._custom_headers = {}
            self._klien = sdk
        return self._klien

    def _argumen(self, instruksi: str, masukan_json: str, skema: dict[str, Any]) -> dict[str, Any]:
        """Menyusun argumen ``messages.stream`` sesuai kebijakan (tanpa alat/sampling)."""
        s = self._s
        arg: dict[str, Any] = {
            "model": self._model,
            "max_tokens": s.ai_max_tokens,
            "system": instruksi,
            "messages": [{"role": "user", "content": masukan_json}],
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": self._effort,
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


_BATAS_PEMBERSIHAN_DETIK = 5


class ClaudeCliKlienModel:
    """``KlienModel`` berbasis CLI headless ``claude -p`` (penyedia ``LANGGANAN_CLAUDE``).

    Aplikasi tidak pernah menerima, menyimpan, atau membaca kredensial langganan: operator
    masuk lewat alur Anthropic sendiri di dalam kontainer, dan CLI membaca sesinya dari
    ``CLAUDE_CONFIG_DIR``. Subprocess hanya menerima env daftar-putih (`env_claude_p`);
    instruksi lewat ``--system-prompt``, masukan pengguna lewat stdin (tidak tampak di
    daftar proses). Stdout, stderr, dan isi prompt tidak pernah dicatat atau dimasukkan ke
    pesan galat. Bentuk keluaran JSON CLI diambil dari dokumentasi resmi dan BELUM diuji
    pada akun nyata, sehingga pengurai gagal-tertutup bila bentuknya berbeda.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        model: str,
        effort: str,
        batas_waktu_detik: float | None = None,
    ) -> None:
        """Menyiapkan klien tanpa menjalankan subprocess.

        Args:
            settings: Pengaturan (``ai_timeout_detik`` dipakai bila ``batas_waktu_detik``
                kosong).
            model: Nama model yang diminta CLI.
            effort: Kedalaman berpikir.
            batas_waktu_detik: Batas waktu satu panggilan ``claude -p`` (untuk uji).
        """
        self._s = settings
        self._model = model
        self._effort = effort
        self._batas = float(batas_waktu_detik or settings.ai_timeout_detik)

    def __repr__(self) -> str:
        """Representasi tanpa data sensitif."""
        return f"ClaudeCliKlienModel(model={self._model!r}, effort={self._effort!r})"

    def _argumen(self, binary: str, instruksi: str, skema: dict[str, Any]) -> list[str]:
        """Susun argumen CLI; masukan pengguna sengaja tidak termasuk (lewat stdin)."""
        return [
            binary,
            "-p",
            "--output-format", "json",
            "--json-schema", json.dumps(skema, ensure_ascii=False, sort_keys=True),
            "--system-prompt", instruksi,
            "--tools", "",
            "--model", self._model,
            "--effort", self._effort,
            "--no-session-persistence",
            "--strict-mcp-config",
            "--setting-sources", "",
        ]  # fmt: skip

    def _jalankan(self, argumen: list[str], masukan: str, cwd: str) -> tuple[int, str]:
        """Jalankan CLI di grup proses sendiri; matikan seluruh grup bila waktu habis.

        Returns:
            ``(exit_code, stdout)``; stderr dibuang di tingkat proses.

        Raises:
            KesalahanModelSementara: Waktu habis (proses dan anak-anaknya sudah dimatikan).
            BinaryClaudeTidakAda: Binary tak dapat dijalankan.
        """
        try:
            proses = subprocess.Popen(
                argumen,
                env=env_claude_p(),
                cwd=cwd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=True,
            )
        except OSError:
            proses = None
        if proses is None:
            # Dilempar di luar `except` agar galat OS (memuat path) tidak ikut terantai.
            raise BinaryClaudeTidakAda("Binary claude tidak dapat dijalankan.")
        waktu_habis = False
        try:
            stdout, _ = proses.communicate(masukan, timeout=self._batas)
        except subprocess.TimeoutExpired:
            # TimeoutExpired membawa cmd/stdout/stderr; tidak dikaitkan ke galat keluar.
            waktu_habis = True
            stdout = ""
        except BaseException:
            self._matikan(proses)
            raise
        if waktu_habis:
            self._matikan(proses)
            logger.warning("model_cli_timeout")
            raise KesalahanModelSementara("Waktu panggilan CLI habis.")
        return proses.returncode, stdout or ""

    @staticmethod
    def _matikan(proses: Any) -> None:
        """SIGKILL ke seluruh grup proses lalu menuai proses (tanpa yatim)."""
        try:
            os.killpg(proses.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proses.kill()
        try:
            proses.communicate(timeout=_BATAS_PEMBERSIHAN_DETIK)
        except Exception as exc:
            logger.warning("model_cli_pembersihan_gagal", extra={"jenis": type(exc).__name__})

    def _urai(self, stdout: str) -> JawabanModel:
        """Urai JSON CLI; bentuk apa pun yang tak dikenali menjadi galat permanen.

        Raises:
            KesalahanModelPermanen: JSON rusak, ``is_error``, ``structured_output`` bukan
                objek, atau jumlah token/model tak terbaca. Pesan tidak memuat keluaran.
        """
        rusak = False
        try:
            data = json.loads(stdout)
        except ValueError:
            data, rusak = None, True  # JSONDecodeError memuat potongan dokumen.
        if rusak:
            raise KesalahanModelPermanen("Keluaran CLI bukan JSON.")
        if not isinstance(data, dict) or data.get("is_error"):
            raise KesalahanModelPermanen("Keluaran CLI tidak sah atau bertanda galat.")
        keluaran = data.get("structured_output")
        if not isinstance(keluaran, dict):
            raise KesalahanModelPermanen("Keluaran CLI tidak memuat structured_output.")
        pakai = data.get("usage")
        per_model = data.get("modelUsage")
        if (
            not isinstance(pakai, dict)
            or not all(isinstance(pakai.get(k), int) for k in ("input_tokens", "output_tokens"))
            or not isinstance(per_model, dict)
            or len(per_model) != 1
        ):
            raise KesalahanModelPermanen("Penggunaan token atau model keluaran CLI tak terbaca.")
        henti = data.get("stop_reason")
        return JawabanModel(
            teks=json.dumps(keluaran, ensure_ascii=False),
            model_dilayani=str(next(iter(per_model))),
            stop_reason=henti if isinstance(henti, str) else None,
            input_tokens=pakai["input_tokens"],
            output_tokens=pakai["output_tokens"],
        )

    def panggil(self, instruksi: str, masukan_json: str, skema: dict[str, Any]) -> JawabanModel:
        """Memanggil Claude lewat ``claude -p`` dan memetakan hasil/galat.

        Status masuk dibaca tepat sebelum panggilan; bila belum masuk, ``claude -p`` tidak
        dijalankan sama sekali.

        Raises:
            BinaryClaudeTidakAda: Binary tidak ada.
            LanggananBelumMasuk: Belum masuk (sebelum panggilan, atau exit bukan nol yang
                disusul status tidak masuk).
            KesalahanModelSementara: Waktu habis.
            KesalahanModelPermanen: Exit bukan nol lain, JSON rusak, atau
                ``structured_output`` tidak ada.
        """
        status = baca_status_cli()
        if not status.terpasang:
            raise BinaryClaudeTidakAda("Binary claude tidak ada.")
        if not status.masuk:
            raise LanggananBelumMasuk("CLI belum masuk ke akun langganan.")
        binary = shutil.which("claude")
        if binary is None:
            raise BinaryClaudeTidakAda("Binary claude tidak ada.")
        with tempfile.TemporaryDirectory(prefix="claude-kerja-") as cwd:
            argumen = self._argumen(binary, instruksi, skema)
            kode, stdout = self._jalankan(argumen, masukan_json, cwd)
        if kode != 0:
            if not baca_status_cli().masuk:
                raise LanggananBelumMasuk("CLI tidak lagi masuk ke akun langganan.")
            logger.warning("model_cli_exit_bukan_nol", extra={"kode": kode})
            raise KesalahanModelPermanen(f"CLI keluar dengan kode {kode}.")
        return self._urai(stdout)
