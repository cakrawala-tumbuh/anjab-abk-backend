"""Pembaca status CLI langganan Claude tanpa menyentuh identitas akun.

Stdout ``claude auth status`` memuat identitas akun, jadi keluarannya dibuang sejak di
tingkat proses; yang dipakai hanya exit code. Subprocess hanya menerima env daftar-putih
sehingga rahasia proses backend tidak pernah sampai ke CLI.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass

__all__ = ["ENV_CLAUDE_P", "StatusCli", "baca_status_cli", "env_claude_p"]

logger = logging.getLogger(__name__)

_BINARY = "claude"
_BATAS_WAKTU_DETIK = 10
_ENV_DIIZINKAN = ("PATH", "HOME", "CLAUDE_CONFIG_DIR")
_PANJANG_VERSI_MAKS = 64

ENV_CLAUDE_P = ("PATH", "HOME", "CLAUDE_CONFIG_DIR", "DISABLE_UPDATES")
"""Daftar-putih env untuk ``claude -p`` (panggilan model): ``_ENV_DIIZINKAN`` ditambah
``DISABLE_UPDATES``. Pembaca status (di atas) sengaja tetap tiga nama."""


@dataclass(frozen=True)
class StatusCli:
    """Status CLI langganan; tidak punya field untuk identitas akun.

    Attributes:
        terpasang: True bila binary ``claude`` ditemukan di ``PATH``.
        masuk: True hanya bila ``claude auth status`` keluar dengan kode 0.
        versi: Baris pertama ``claude --version``, atau ``None`` bila tak terbaca.
    """

    terpasang: bool
    masuk: bool
    versi: str | None


def _env_daftar_putih() -> dict[str, str]:
    """Salin hanya variabel `_ENV_DIIZINKAN` yang memang diset di proses ini."""
    return {nama: os.environ[nama] for nama in _ENV_DIIZINKAN if nama in os.environ}


def env_claude_p() -> dict[str, str]:
    """Env persis untuk subprocess ``claude -p``: empat nama `ENV_CLAUDE_P`, tidak lebih.

    ``DISABLE_UPDATES`` bernilai ``1`` bila proses induk tidak menyetelnya, sehingga CLI
    tidak pernah memperbarui dirinya sendiri. Variabel lain (``ANTHROPIC_API_KEY``,
    ``AI_KREDENSIAL_KUNCI_INDUK``, ``CLAUDE_CODE_OAUTH_TOKEN``, ``ANTHROPIC_BASE_URL``,
    dst.) tidak pernah disalin.

    Returns:
        Kamus env baru; mengubahnya tidak memengaruhi ``os.environ``.
    """
    env = {nama: os.environ[nama] for nama in ENV_CLAUDE_P if nama in os.environ}
    env.setdefault("DISABLE_UPDATES", "1")
    return env


def _catat_gagal(operasi: str, exc: Exception) -> None:
    """Catat kegagalan subprocess dengan nama jenis galat saja, tanpa isi galatnya."""
    logger.warning("ai_cli_gagal", extra={"operasi": operasi, "jenis": type(exc).__name__})


def _baca_versi(binary: str) -> str | None:
    """Baris pertama ``claude --version``; ``None`` bila gagal, timeout, atau kosong."""
    try:
        hasil = subprocess.run(
            [binary, "--version"],
            env=_env_daftar_putih(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=_BATAS_WAKTU_DETIK,
            text=True,
            errors="replace",
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        _catat_gagal("version", exc)
        return None
    if hasil.returncode != 0 or not hasil.stdout:
        return None
    baris = hasil.stdout.strip().splitlines()
    return baris[0].strip()[:_PANJANG_VERSI_MAKS] or None if baris else None


def _sudah_masuk(binary: str) -> bool:
    """Exit code ``claude auth status``: 0 berarti masuk. Keluarannya tidak pernah dibaca."""
    try:
        hasil = subprocess.run(
            [binary, "auth", "status"],
            env=_env_daftar_putih(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=_BATAS_WAKTU_DETIK,
            check=False,
        )
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        _catat_gagal("auth_status", exc)
        return False
    return hasil.returncode == 0


def baca_status_cli() -> StatusCli:
    """Baca status CLI langganan; tidak pernah melempar galat.

    Menjalankan paling banyak dua subprocess, masing-masing dibatasi 10 detik, sehingga
    pemanggil dapat tertahan sampai sekitar 20 detik. Binary yang tidak ada dibalas seketika
    tanpa subprocess.

    Returns:
        Status CLI. Timeout atau galat apa pun menghasilkan ``masuk=False``.
    """
    binary = shutil.which(_BINARY)
    if binary is None:
        return StatusCli(terpasang=False, masuk=False, versi=None)
    return StatusCli(terpasang=True, masuk=_sudah_masuk(binary), versi=_baca_versi(binary))
