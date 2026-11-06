"""Perakitan masukan model yang dipakai bersama worker dan harness evaluasi.

Worker (``ai/worker.py``) dan harness evaluasi (``evals/``) wajib mengirim ke model
byte-per-byte masukan yang sama untuk kasus yang sama; jika tidak, hasil evaluasi tidak
berlaku untuk produksi. Karena itu perakitan tidak ditulis dua kali: keduanya memanggil
fungsi di modul ini. Modul ini murni (tanpa basis data, jaringan, atau pengaturan).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["POLA_PERIODE_AI", "peta_sumber", "susun_masukan_json"]

POLA_PERIODE_AI = r"^[A-Za-z0-9_.:/-]+$"
"""Pola ``periode`` pada parameter fungsi AI (P01, P04, P10).

Sama dengan pola parameter kode lain ditambah garis miring, agar ``2026/27`` sah. Spasi tetap
ditolak.
"""


def peta_sumber(sumber: Sequence[Mapping[str, Any]]) -> dict[str, tuple[str, str]]:
    """Petakan daftar sumber masukan menjadi bentuk yang dibaca ``cek_keluaran``.

    Args:
        sumber: Elemen ``masukan["sumber"]`` run; tiap elemen memuat ``source_id``,
            ``source_hash``, dan ``teks``.

    Returns:
        ``source_id`` -> ``(source_hash, teks)``.
    """
    return {x["source_id"]: (x["source_hash"], x["teks"]) for x in sumber}


def susun_masukan_json(masukan: Mapping[str, Any]) -> str:
    """Susun pesan pengguna yang dikirim ke model dari masukan run.

    Hanya ``sumber`` dan ``parameter`` yang ikut; kunci lain (mis. ``ref_id``) tidak
    pernah dikirim ke model. Kunci diurutkan agar keluaran deterministik.

    Args:
        masukan: Masukan run dengan kunci ``sumber`` dan ``parameter``.

    Returns:
        String JSON (``ensure_ascii=False``, ``sort_keys=True``).
    """
    return json.dumps(
        {"sumber": masukan["sumber"], "parameter": masukan["parameter"]},
        ensure_ascii=False,
        sort_keys=True,
    )
