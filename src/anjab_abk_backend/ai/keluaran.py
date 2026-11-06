"""Pemeriksa deterministik keluaran model: bentuk amplop dan kebenaran sitasi.

Structured output menjamin bentuk, bukan kebenaran kutipan. Modul ini
memvalidasi ulang di sisi klien dan memutuskan keluaran model ``LOLOS``,
``EVIDENCE_GAP``, atau ``KARANTINA`` beserta kode alasannya. Yang tidak bisa
diperiksa mesin (mis. makna parafrasa) tetap tugas reviewer manusia; karena itu
``human_review_required`` selalu ``true``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from jsonschema import Draft202012Validator

__all__ = ["HasilCek", "KODE_KARANTINA", "cek_keluaran", "normalkan_kutipan", "skema_dengan_amplop"]

StatusQa = Literal["LOLOS", "EVIDENCE_GAP", "KARANTINA"]

KODE_KARANTINA = (
    "JSON_TIDAK_SAH",
    "SKEMA_TIDAK_SAH",
    "SUMBER_FIKTIF",
    "HASH_TIDAK_COCOK",
    "KUTIPAN_TIDAK_DITEMUKAN",
    "TANPA_SITASI",
    "KUTIPAN_KOSONG",
    "GAP_TANPA_ALASAN",
)

_RE_SPASI = re.compile(r"\s+")


@dataclass(frozen=True)
class HasilCek:
    """Keputusan ``cek_keluaran``.

    Attributes:
        status_qa: ``LOLOS``, ``EVIDENCE_GAP``, atau ``KARANTINA``.
        kode: Kode alasan karantina, urut tampil, tanpa duplikat. Kosong bila
            tidak karantina.
        keluaran: Objek keluaran hasil parse; ``None`` bila karantina.
    """

    status_qa: StatusQa
    kode: tuple[str, ...]
    keluaran: dict[str, Any] | None


def skema_dengan_amplop(skema_isi: dict[str, Any]) -> dict[str, Any]:
    """Membungkus skema isi dengan amplop keluaran bersama.

    Skema hasil hanya memakai fitur yang didukung structured output: semua
    objek ``additionalProperties: false`` dan seluruh field ``required``; tanpa
    ``minLength``, ``minimum``, atau ``minItems`` (syarat itu diperiksa
    ``cek_keluaran``).

    Args:
        skema_isi: Skema milik fungsi untuk field ``isi``. Disalin, tidak diubah.

    Returns:
        Skema amplop lengkap dengan ``isi`` berisi ``skema_isi``.
    """
    ref = {
        "type": "object",
        "additionalProperties": False,
        "required": ["source_id", "source_hash"],
        "properties": {
            "source_id": {"type": "string"},
            "source_hash": {"type": "string"},
        },
    }
    span = {
        "type": "object",
        "additionalProperties": False,
        "required": ["source_id", "span"],
        "properties": {
            "source_id": {"type": "string"},
            "span": {"type": "string"},
        },
    }
    teks = {"type": "array", "items": {"type": "string"}}
    properti = {
        "status": {"type": "string", "enum": ["AI_DRAFT", "EVIDENCE_GAP"]},
        "source_refs": {"type": "array", "items": ref},
        "cited_spans": {"type": "array", "items": span},
        "confidence_reason": {"type": "string"},
        "unknowns": teks,
        "contradictions": teks,
        "human_review_required": {"type": "boolean", "const": True},
        "isi": json.loads(json.dumps(skema_isi)),
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": list(properti),
        "properties": properti,
    }


def normalkan_kutipan(teks: str) -> str:
    """Menormalkan spasi kutipan: rangkaian spasi/baris menjadi satu spasi, tepi dipangkas.

    Dipakai bersama oleh ``cek_keluaran`` dan aturan isi per fungsi (mis. ``aturan_p01``) agar
    perbandingan kutipan memakai satu definisi spasi. Huruf besar-kecil dipertahankan.

    Args:
        teks: Teks kutipan mentah.

    Returns:
        Teks dengan spasi ternormalkan; string kosong bila ``teks`` hanya spasi.
    """
    return _RE_SPASI.sub(" ", teks).strip()


def cek_keluaran(
    teks_json: str,
    skema: dict[str, Any],
    sumber: Mapping[str, tuple[str, str]],
) -> HasilCek:
    """Memutuskan nasib keluaran model.

    Urutan: parse JSON, validasi skema, lalu pemeriksaan sitasi. Pelanggaran
    sitasi dilaporkan seluruhnya, tidak berhenti di yang pertama. Kutipan cocok
    bila ``span`` (spasi dinormalkan) adalah substring teks sumber ber-
    ``source_id`` sama; pencocokan peka huruf besar-kecil.

    Args:
        teks_json: Keluaran mentah model.
        skema: Skema dari ``skema_dengan_amplop``.
        sumber: ``source_id`` -> ``(source_hash, teks)`` milik masukan yang
            sudah disamarkan.

    Returns:
        ``HasilCek``; ``LOLOS`` untuk ``AI_DRAFT`` tanpa pelanggaran,
        ``EVIDENCE_GAP`` untuk celah bukti tanpa pelanggaran, selain itu
        ``KARANTINA``.
    """
    try:
        data = json.loads(teks_json)
    except (ValueError, TypeError):
        return HasilCek("KARANTINA", ("JSON_TIDAK_SAH",), None)

    if any(Draft202012Validator(skema).iter_errors(data)) or not isinstance(data, dict):
        return HasilCek("KARANTINA", ("SKEMA_TIDAK_SAH",), None)

    kode: list[str] = []

    def tandai(k: str) -> None:
        if k not in kode:
            kode.append(k)

    fiktif: set[str] = set()
    for ref in data["source_refs"]:
        sid = ref["source_id"]
        if sid not in sumber:
            tandai("SUMBER_FIKTIF")
            fiktif.add(sid)
        elif ref["source_hash"] != sumber[sid][0]:
            tandai("HASH_TIDAK_COCOK")

    for kutip in data["cited_spans"]:
        sid = kutip["source_id"]
        if sid not in sumber:
            tandai("SUMBER_FIKTIF")
            continue
        span = normalkan_kutipan(kutip["span"])
        if not span:
            tandai("KUTIPAN_KOSONG")
        elif span not in normalkan_kutipan(sumber[sid][1]):
            tandai("KUTIPAN_TIDAK_DITEMUKAN")

    status = data["status"]
    if status == "AI_DRAFT" and not data["cited_spans"]:
        tandai("TANPA_SITASI")
    if status == "EVIDENCE_GAP" and not any(normalkan_kutipan(u) for u in data["unknowns"]):
        tandai("GAP_TANPA_ALASAN")

    if kode:
        return HasilCek("KARANTINA", tuple(kode), None)
    return HasilCek("LOLOS" if status == "AI_DRAFT" else "EVIDENCE_GAP", (), data)
