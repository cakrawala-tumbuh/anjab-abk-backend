"""Pelari evaluasi perilaku model: ``python -m evals.jalankan --fungsi P10 --penyedia <jalur>``.

Menjalankan kasus sintetis lewat jalur yang dipilih operator (``API_ANTHROPIC`` atau
``LANGGANAN_CLAUDE``) dan menghasilkan vonis ber-exit-code. Tanpa basis data, tanpa
``AiGateway``, tanpa flag fitur. Alur per kasus ``MODEL``: ``gerbang_masukan`` ->
instruksi ``GUARDRAIL_V1`` + instruksi fungsi -> ``klien.panggil`` dengan
``skema_dengan_amplop`` -> evaluasi worker (``cek_keluaran`` + ``periksa_pii`` keluaran)
-> penilai. Perakitan masukan dan evaluasi keluaran memakai kode yang sama dengan worker.

Laporan hanya ke stdout: satu baris JSON per ulangan, lalu SATU baris ``#EVAL`` terakhir yang
selalu tercetak (juga pada exit 2 dan galat tak terduga). ``make`` mengubah kegagalan resep
menjadi exit 2, jadi kode harness dibaca dari ``exit=`` pada baris itu.

Exit: 0 lulus; 1 gagal perilaku; 2 argumen/kasus rusak (atau galat tak terduga); 3 kunci tak
ada; 4 tak konklusif; 5 gagal permanen; 6 langganan belum masuk; 7 binary ``claude`` tak ada.

Kunci API hanya dibaca dari ``ANTHROPIC_API_KEY`` pada jalur API, di fungsi ``_buat_klien``
(satu-satunya pembaca), dan tidak pernah dicetak.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, NoReturn, TextIO

from anjab_abk_backend.ai.gateway import _ALASAN_EVIDENCE_GAP
from anjab_abk_backend.ai.guardrail import susun_instruksi
from anjab_abk_backend.ai.keluaran import skema_dengan_amplop
from anjab_abk_backend.ai.klien import (
    AnthropicKlienModel,
    BinaryClaudeTidakAda,
    ClaudeCliKlienModel,
    JawabanModel,
    KesalahanModelPermanen,
    KesalahanModelSementara,
    KlienModel,
    KunciModelTidakAda,
    LanggananBelumMasuk,
)
from anjab_abk_backend.ai.langganan_cli import baca_status_cli
from anjab_abk_backend.ai.masukan import peta_sumber, susun_masukan_json
from anjab_abk_backend.ai.penyedia import AI_EFFORT_BAWAAN, AI_MODEL_BAWAAN
from anjab_abk_backend.ai.redaksi import SumberAi, gerbang_masukan, periksa_pii
from anjab_abk_backend.ai.worker import _evaluasi
from anjab_abk_backend.config import Settings

from .kasus import DEFINISI_FUNGSI, DefinisiFungsi, Kasus, KasusRusak, muat_kasus
from .penilai import nilai

__all__ = ["PENYEDIA_SAH", "main"]

PENYEDIA_SAH = ("API_ANTHROPIC", "LANGGANAN_CLAUDE")
_ULANG_BAWAAN = 3
_MAKS_TOKEN_BAWAAN = 500_000
_ULANG_SEMENTARA = 2
_RE_NILAI_EVAL = re.compile(r"[^A-Za-z0-9_.:-]")


class Berhenti(Exception):
    """Hentikan evaluasi dengan ``kode`` dan ``keluar`` (kode exit harness)."""

    def __init__(self, kode: str, keluar: int, pesan: str = "") -> None:
        """Simpan kode alasan, kode exit, dan pesan opsional untuk stderr."""
        super().__init__(pesan or kode)
        self.kode = kode
        self.keluar = keluar
        self.pesan = pesan


@dataclass
class _Keadaan:
    """Nilai yang dicetak pada baris ``#EVAL`` dan diperbarui selama jalan."""

    penyedia: str = "-"
    model: str = AI_MODEL_BAWAAN
    effort: str = AI_EFFORT_BAWAAN
    geo: str = "-"
    fallback: str = "-"
    token: int = 0
    panggilan: int = 0
    kasus_lulus: int = 0
    kasus_gagal: int = 0
    kode: str = "GALAT_TAK_TERDUGA"
    keluar: int = 2
    extra: dict[str, Any] = field(default_factory=dict)


def _tidur(detik: float) -> None:
    """Jeda sebelum mengulang galat sementara (diganti di uji)."""
    time.sleep(detik)


class _Parser(argparse.ArgumentParser):
    """``ArgumentParser`` yang tidak mencetak/keluar sendiri; galat menjadi ``Berhenti``."""

    def error(self, message: str) -> NoReturn:  # noqa: D102 - override argparse
        raise Berhenti("ARGUMEN_RUSAK", 2, message)


def _int_env(env: Mapping[str, str], nama: str, bawaan: int) -> int:
    """Baca bilangan bulat positif dari env; kosong/tak ada = ``bawaan``."""
    mentah = (env.get(nama) or "").strip()
    if not mentah:
        return bawaan
    try:
        nilai_ = int(mentah)
    except ValueError:
        raise Berhenti("ARGUMEN_RUSAK", 2, f"{nama} bukan bilangan bulat") from None
    if nilai_ < 1:
        raise Berhenti("ARGUMEN_RUSAK", 2, f"{nama} harus >= 1")
    return nilai_


def _bool_env(env: Mapping[str, str], nama: str, bawaan: bool) -> bool:
    """Baca boolean (true/false/1/0) dari env; kosong/tak ada = ``bawaan``."""
    mentah = (env.get(nama) or "").strip().lower()
    if not mentah:
        return bawaan
    if mentah in ("true", "1"):
        return True
    if mentah in ("false", "0"):
        return False
    raise Berhenti("ARGUMEN_RUSAK", 2, f"{nama} bukan boolean")


def _buat_klien(penyedia: str, settings: Settings, env: Mapping[str, str]) -> KlienModel:
    """Periksa prasyarat jalur lalu bangun klien dengan model dan effort bawaan eksplisit.

    Satu-satunya tempat ``ANTHROPIC_API_KEY`` dibaca, dan hanya pada jalur API. Jalur
    langganan tidak menyentuh env itu sama sekali.

    Args:
        penyedia: ``API_ANTHROPIC`` atau ``LANGGANAN_CLAUDE``.
        settings: Pengaturan untuk klien.
        env: Environment (hanya diakses lewat ``get``).

    Returns:
        Klien siap pakai; belum ada panggilan model.

    Raises:
        Berhenti: kunci tak ada (3), binary tak ada (7), atau belum masuk (6).
    """
    if penyedia == "API_ANTHROPIC":
        kunci = (env.get("ANTHROPIC_API_KEY") or "").strip()
        if not kunci:
            raise Berhenti("KUNCI_TIDAK_ADA", 3)
        return AnthropicKlienModel(
            settings, kunci_api=kunci, model=AI_MODEL_BAWAAN, effort=AI_EFFORT_BAWAAN
        )
    status = baca_status_cli()
    if not status.terpasang:
        raise Berhenti("BINARY_CLAUDE_TIDAK_ADA", 7)
    if not status.masuk:
        raise Berhenti("LANGGANAN_BELUM_MASUK", 6)
    return ClaudeCliKlienModel(settings, model=AI_MODEL_BAWAAN, effort=AI_EFFORT_BAWAAN)


def _gerbang(kasus: Kasus, settings: Settings) -> tuple[str | None, list[SumberAi]]:
    """Jalankan gerbang masukan seperti ``AiGateway.ajukan`` (tanpa basis data).

    Returns:
        ``(alasan, sumber_bersih)``; ``alasan`` ``None`` bila lolos.
    """
    alasan: str | None = None
    bersih: list[SumberAi] = []
    kamus = list(kasus.kamus_nama)
    if not kasus.sumber:
        alasan = "SUMBER_KOSONG"
    for s in kasus.sumber:
        hash_ = s.source_hash
        if hash_ is None:
            hash_ = hashlib.sha256(s.teks.encode("utf-8")).hexdigest()
        hasil = gerbang_masukan(
            SumberAi(source_id=s.source_id, source_hash=hash_, jenis=s.jenis, teks=s.teks),
            kamus,
            settings,
        )
        if not hasil.lolos or hasil.sumber is None:
            alasan = hasil.alasan or "SUMBER_KOSONG"
            break
        bersih.append(hasil.sumber)
    if (
        alasan is None
        and periksa_pii(json.dumps(kasus.parameter, ensure_ascii=False), kamus).temuan
    ):
        alasan = "PII_DITEMUKAN"
    return alasan, bersih


def rakit_masukan(bersih: list[SumberAi], parameter: dict[str, Any]) -> dict[str, Any]:
    """Rakit ``masukan`` run dengan bentuk yang sama dengan ``AiGateway.ajukan``.

    Args:
        bersih: Sumber yang lolos gerbang.
        parameter: Parameter fungsi.

    Returns:
        Kamus ``sumber``/``parameter``/``ref_id`` (``ref_id`` ``None``); dikirim ke model
        lewat ``susun_masukan_json`` yang dipakai worker.
    """
    return {
        "sumber": [
            {
                "source_id": s.source_id,
                "source_hash": s.source_hash,
                "jenis": s.jenis,
                "teks": s.teks,
            }
            for s in bersih
        ],
        "parameter": parameter,
        "ref_id": None,
    }


def _panggil(
    klien: KlienModel, st: _Keadaan, args: tuple[str, str, dict[str, Any]]
) -> JawabanModel:
    """Panggil model; ulangi ``KesalahanModelSementara`` dua kali; petakan galat ke ``Berhenti``."""
    instruksi, masukan_json, skema = args
    for percobaan in range(_ULANG_SEMENTARA + 1):
        try:
            st.panggilan += 1
            return klien.panggil(instruksi, masukan_json, skema)
        except KesalahanModelSementara:
            if percobaan == _ULANG_SEMENTARA:
                raise Berhenti("TAK_KONKLUSIF", 4, "galat sementara berulang") from None
            _tidur(2.0**percobaan)
        except KesalahanModelPermanen:
            kode = "SKEMA_DITOLAK_API" if st.penyedia == "API_ANTHROPIC" else "CLI_GAGAL_PERMANEN"
            raise Berhenti(kode, 5) from None
        except KunciModelTidakAda:
            raise Berhenti("KUNCI_TIDAK_ADA", 3) from None
        except LanggananBelumMasuk:
            raise Berhenti("LANGGANAN_BELUM_MASUK", 6) from None
        except BinaryClaudeTidakAda:
            raise Berhenti("BINARY_CLAUDE_TIDAK_ADA", 7) from None
    raise AssertionError("tak tercapai")  # pragma: no cover


def _laporan(out: TextIO, baris: dict[str, Any]) -> None:
    """Cetak satu baris JSON laporan ke stdout."""
    out.write(json.dumps(baris, ensure_ascii=False) + "\n")
    out.flush()


def _jalankan_kasus(
    kasus: Kasus,
    definisi_fungsi: DefinisiFungsi,
    klien: KlienModel | None,
    settings: Settings,
    st: _Keadaan,
    ulang: int,
    maks_token: int,
    out: TextIO,
) -> bool:
    """Jalankan satu kasus; kembalikan ``True`` bila semua ulangannya lulus."""
    alasan, bersih = _gerbang(kasus, settings)
    h = kasus.harapan
    if h.jalur == "TANPA_MODEL":
        status = "EVIDENCE_GAP" if alasan in _ALASAN_EVIDENCE_GAP else "DIBLOKIR"
        pel: list[str] = []
        if alasan != h.alasan_gerbang:
            pel.append(f"GERBANG_TIDAK_SESUAI:{alasan or 'LOLOS'}")
        _laporan(
            out,
            {
                "id": kasus.id, "ulangan": 1, "jalur": "TANPA_MODEL", "status_qa": status,
                "kode": [alasan] if alasan else [], "pelanggaran": pel, "panggilan_model": 0,
                "lulus": not pel,
            },
        )  # fmt: skip
        return not pel
    if alasan is not None or klien is None:
        _laporan(
            out,
            {
                "id": kasus.id, "ulangan": 1, "jalur": "MODEL", "status_qa": "DIBLOKIR",
                "kode": [alasan or "TANPA_KLIEN"], "pelanggaran": ["GERBANG_MENOLAK_KASUS_MODEL"],
                "panggilan_model": 0, "lulus": False,
            },
        )  # fmt: skip
        return False

    masukan = rakit_masukan(bersih, kasus.parameter)
    argumen = (
        susun_instruksi(definisi_fungsi.fungsi.instruksi),
        susun_masukan_json(masukan),
        skema_dengan_amplop(definisi_fungsi.fungsi.skema_isi),
    )
    semua = True
    for ke in range(1, ulang + 1):
        if st.token >= maks_token:
            raise Berhenti("BATAS_TOKEN", 4, "batas token tercapai")
        jawaban = _panggil(klien, st, argumen)
        st.token += jawaban.input_tokens + jawaban.output_tokens
        status_enum, kode, keluaran = _evaluasi(
            jawaban, definisi_fungsi.fungsi, peta_sumber(masukan["sumber"]), list(kasus.kamus_nama)
        )
        pel = nilai(kasus, status_enum.value, kode, keluaran, definisi_fungsi.fungsi.kode)
        _laporan(
            out,
            {
                "id": kasus.id, "ulangan": ke, "jalur": "MODEL", "status_qa": status_enum.value,
                "kode": kode, "pelanggaran": pel, "model_dilayani": jawaban.model_dilayani,
                "stop_reason": jawaban.stop_reason, "input_tokens": jawaban.input_tokens,
                "output_tokens": jawaban.output_tokens, "teks": jawaban.teks, "lulus": not pel,
            },
        )  # fmt: skip
        semua = semua and not pel
    return semua


def _jalankan(argv: list[str], env: Mapping[str, str], out: TextIO, st: _Keadaan) -> int:
    """Isi evaluasi: argumen -> kasus -> klien -> kasus satu per satu. Lihat ``main``."""
    parser = _Parser(add_help=False)
    parser.add_argument("--fungsi", required=True)
    parser.add_argument("--penyedia", required=True)
    parser.add_argument("--kasus", default=None)
    try:
        ns = parser.parse_args(argv)
    except SystemExit:  # pragma: no cover - parser tidak keluar sendiri
        raise Berhenti("ARGUMEN_RUSAK", 2) from None
    if ns.penyedia not in PENYEDIA_SAH:
        raise Berhenti("PENYEDIA_TIDAK_DIKENAL", 2, "penyedia tidak dikenal")
    st.penyedia = ns.penyedia
    definisi = DEFINISI_FUNGSI.get(ns.fungsi)
    if definisi is None:
        raise Berhenti("FUNGSI_TIDAK_DIKENAL", 2, "fungsi tidak dikenal")
    ulang = _int_env(env, "EVAL_ULANG", _ULANG_BAWAAN)
    maks_token = _int_env(env, "EVAL_MAKS_TOKEN", _MAKS_TOKEN_BAWAAN)
    api = ns.penyedia == "API_ANTHROPIC"
    geo = (env.get("AI_INFERENCE_GEO") or "").strip() if api else ""
    fallback = _bool_env(env, "AI_REFUSAL_FALLBACK", True) if api else True
    if api:
        st.geo, st.fallback = geo or "-", str(fallback).lower()
    kasus = muat_kasus(Path(ns.kasus) if ns.kasus else definisi.berkas, ns.fungsi, definisi)
    try:
        settings = Settings(
            _env_file=None,
            ai_jenis_sumber_diizinkan=["SINTETIS"],
            ai_pii_mode="BLOKIR",
            ai_inference_geo=geo,
            ai_refusal_fallback=fallback,
        )
    except Exception as exc:
        raise Berhenti("PENGATURAN_RUSAK", 2, type(exc).__name__) from None
    klien = _buat_klien(ns.penyedia, settings, env)
    for k in kasus:
        if _jalankan_kasus(k, definisi, klien, settings, st, ulang, maks_token, out):
            st.kasus_lulus += 1
        else:
            st.kasus_gagal += 1
    if st.kasus_gagal:
        st.kode = "GAGAL_PERILAKU"
        return 1
    st.kode = "LULUS"
    return 0


def _nilai_eval(nilai_: object) -> str:
    """Bersihkan nilai untuk baris ``#EVAL`` (satu token, tanpa spasi/baris baru)."""
    return _RE_NILAI_EVAL.sub("?", str(nilai_)) or "-"


def main(
    argv: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Titik masuk harness; SELALU mencetak baris ``#EVAL`` terakhir ke ``out``.

    Args:
        argv: Argumen (bawaan ``sys.argv[1:]``): ``--fungsi``, ``--penyedia``, ``--kasus``.
        env: Environment (bawaan ``os.environ``): ``ANTHROPIC_API_KEY`` (hanya jalur API),
            ``EVAL_ULANG``, ``EVAL_MAKS_TOKEN``, ``AI_INFERENCE_GEO``, ``AI_REFUSAL_FALLBACK``.
        out: Aliran stdout.
        err: Aliran stderr (pesan singkat tanpa data sensitif).

    Returns:
        Kode exit harness (lihat docstring modul).
    """
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    out = out or sys.stdout
    err = err or sys.stderr
    st = _Keadaan()
    try:
        st.keluar = _jalankan(argv, env, out, st)
    except Berhenti as b:
        st.kode, st.keluar = b.kode, b.keluar
        if b.pesan:
            err.write(f"{b.kode}: {b.pesan}\n")
    except KasusRusak as k:
        st.kode, st.keluar = "KASUS_RUSAK", 2
        err.write(f"KASUS_RUSAK: {k}\n")
    except Exception as exc:
        st.kode, st.keluar = "GALAT_TAK_TERDUGA", 2
        err.write(f"GALAT_TAK_TERDUGA: {type(exc).__name__}\n")
    campur = {
        "penyedia": st.penyedia, "model": st.model, "effort": st.effort, "kode": st.kode,
        "exit": st.keluar, "geo": st.geo, "fallback": st.fallback, "kasus_lulus": st.kasus_lulus,
        "kasus_gagal": st.kasus_gagal, "token": st.token, "panggilan": st.panggilan,
    }  # fmt: skip
    out.write("#EVAL " + " ".join(f"{k}={_nilai_eval(v)}" for k, v in campur.items()) + "\n")
    out.flush()
    return st.keluar


if __name__ == "__main__":
    raise SystemExit(main())
