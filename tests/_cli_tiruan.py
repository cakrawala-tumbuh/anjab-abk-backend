"""Tiruan subprocess ``claude`` untuk uji driver CLI (#112). Tanpa kredensial, tanpa jaringan."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from anjab_abk_backend.ai import klien as modul_klien
from anjab_abk_backend.ai.langganan_cli import StatusCli

SUREL = "rahasia.sintetis@example.test"
"""Penanda: tidak boleh muncul di ai_run, log, atau pesan galat."""


def keluaran_cli(isi: dict[str, Any] | None = None, **tambah: Any) -> str:
    """JSON keluaran CLI tiruan berbentuk dokumentasi resmi (belum diuji pada akun nyata)."""
    data: dict[str, Any] = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "",
        "stop_reason": "end_turn",
        "structured_output": {"ringkas": "ok"} if isi is None else isi,
        "usage": {"input_tokens": 11, "output_tokens": 5},
        "modelUsage": {"claude-opus-5-5": {"inputTokens": 11, "outputTokens": 5}},
    }
    data.update(tambah)
    return json.dumps(data)


class PopenTiruan:
    """Pengganti ``subprocess.Popen``: mencatat argumen, tidak menjalankan apa pun."""

    daftar: list[PopenTiruan] = []
    stdout = ""
    kode = 0
    galat_waktu = False

    def __init__(self, args: list[str], **kw: Any) -> None:
        self.args, self.kw = args, kw
        self.masukan: str | None = None
        self.pid = 4_000_000  # tidak mungkin pid nyata; killpg ditiru juga
        self.returncode: int | None = None
        self.dibunuh = False
        PopenTiruan.daftar.append(self)

    def communicate(self, masukan: str | None = None, timeout: float | None = None):
        if masukan is not None:
            self.masukan = masukan
        if PopenTiruan.galat_waktu and not self.dibunuh:
            raise subprocess.TimeoutExpired(
                self.args, timeout or 0, output=SUREL.encode(), stderr=SUREL.encode()
            )
        self.returncode = PopenTiruan.kode
        return PopenTiruan.stdout, None

    def kill(self) -> None:
        self.dibunuh = True


def pasang(
    monkeypatch: Any,
    *,
    terpasang: bool = True,
    masuk: list[bool] | bool = True,
    stdout: str | None = None,
    kode: int = 0,
    galat_waktu: bool = False,
) -> list[int]:
    """Pasang tiruan ``Popen``, ``which``, ``baca_status_cli``, dan ``killpg``.

    Returns:
        Daftar pid yang dikirimi ``killpg`` (diisi saat uji berjalan).
    """
    PopenTiruan.daftar = []
    PopenTiruan.stdout = keluaran_cli() if stdout is None else stdout
    PopenTiruan.kode = kode
    PopenTiruan.galat_waktu = galat_waktu
    antrean = list(masuk) if isinstance(masuk, list) else None
    dibunuh: list[int] = []

    def status() -> StatusCli:
        if not terpasang:
            return StatusCli(terpasang=False, masuk=False, versi=None)
        nilai = (antrean.pop(0) if len(antrean) > 1 else antrean[0]) if antrean else masuk
        return StatusCli(terpasang=True, masuk=bool(nilai), versi="2.1.311 (Claude Code)")

    def killpg(pid: int, _sinyal: int) -> None:
        dibunuh.append(pid)
        for p in PopenTiruan.daftar:
            if p.pid == pid:
                p.dibunuh = True

    monkeypatch.setattr(modul_klien, "baca_status_cli", status)
    biner = "/usr/bin/claude" if terpasang else None
    monkeypatch.setattr(modul_klien.shutil, "which", lambda _n: biner)
    monkeypatch.setattr(modul_klien.subprocess, "Popen", PopenTiruan)
    monkeypatch.setattr(modul_klien.os, "killpg", killpg)
    return dibunuh
