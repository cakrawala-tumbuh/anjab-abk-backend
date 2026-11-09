"""Definisi fungsi AI P06: draf opsi redesain dan asumsi skenario, di belakang gerbang F4.

P06 (library prompt YPII, Option & T2-K Scenario Drafter, PRM:42-46) menyusun opsi status quo,
simplify, automate, dan transfer untuk satu masalah redesain, masing-masing dengan fakta
bersumber dan asumsinya, serta parameter yang belum diketahui. P06 tidak menghitung FTE dan
tidak menetapkan formasi (PRM:9, PRM:91), dan tidak pernah memberi status VERIFIED atau
READY/APPROVE (KAI:16).

Pengajuan hanya sah untuk masalah yang lolos gerbang F4 (``ai/syarat_f4.py``, definisi
sementara ``VERSI_SYARAT_F4``). Sumbernya ``rakit_sumber_redesain`` (dengan konfirmasi
terkirim) ditambah ``rakit_sumber_alternatif``; tidak ada kuantitas terverifikasi yang dikirim
(``source_verified_quantities`` selalu kosong). Hasilnya hanya usulan di ``ai_usulan``; tab
Alternatif tidak diisi otomatis.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field

from ..redesain.schemas.kosakata import OpsiAlternatif
from .gateway import FungsiAi
from .masukan import POLA_PERIODE_AI
from .syarat_f4 import VERSI_SYARAT_F4

__all__ = [
    "FUNGSI_P06",
    "INSTRUKSI_P06",
    "JENIS_OPSI_P06",
    "KODE_ANGKA_FTE",
    "KODE_RUJUKAN_TAK_DIKENAL",
    "KODE_STATUS_TERLARANG",
    "OPSI_APLIKASI_P06",
    "SKEMA_ISI_P06",
    "ParameterP06",
    "aturan_p06",
]

JENIS_OPSI_P06 = ("STATUS_QUO", "SIMPLIFY", "AUTOMATE", "TRANSFER")
"""Empat jenis opsi library prompt P06."""

OPSI_APLIKASI_P06: tuple[str, ...] = get_args(OpsiAlternatif)
"""Tujuh opsi alternatif aplikasi (``OpsiAlternatif``) yang boleh dipetakan dari jenis opsi."""

KODE_RUJUKAN_TAK_DIKENAL = "RUJUKAN_TAK_DIKENAL"
"""Kode pelanggaran: ada ``fakta_sumber[].source_ids`` yang tidak tercantum di
``amplop.source_refs``, atau daftarnya kosong (minimal satu ditagih di sini karena konvensi skema
repo tidak memakai ``minItems`` untuk field ini)."""

KODE_STATUS_TERLARANG = "STATUS_TERLARANG"
"""Kode pelanggaran: ada string isi yang memuat kata utuh ``VERIFIED``, ``READY``, atau
``APPROVE`` (tak peka huruf). AI dilarang memberi status itu (KAI:16)."""

KODE_ANGKA_FTE = "ANGKA_FTE"
"""Kode pelanggaran: ada string isi yang memuat angka diikuti ``FTE`` (mis. ``1,5 FTE``). P06
tidak menghitung FTE maupun formasi."""

_RE_STATUS_TERLARANG = re.compile(r"\b(?:VERIFIED|READY|APPROVE)\b", re.IGNORECASE)
_RE_ANGKA_FTE = re.compile(r"\d+(?:[.,]\d+)?\s*FTE\b", re.IGNORECASE)

INSTRUKSI_P06 = """\
Fungsi: menyusun draf opsi redesain untuk satu masalah redesain sekolah beserta asumsi \
skenarionya. Sumber berpenanda "masalah:", "proses:", "langkah:", "bukti:", "koreksi:", dan \
"konfirmasi:" memuat data masalah yang klaimnya sudah diperkuat Tim; "alternatif:" memuat \
alternatif yang sudah dicatat Tim, termasuk satu jabatan penerima (pihak_penerima_jabatan_id) \
bila ada. Orang hanya disebut lewat kode samaran. Hasilnya hanya usulan untuk Tim Kajian; \
bukan keputusan.

Aturan fungsi:
1. Susun opsi dengan jenis STATUS_QUO, SIMPLIFY, AUTOMATE, atau TRANSFER. Petakan ke \
opsi_aplikasi bila padanannya jelas: STATUS_QUO ke "Pertahankan"; SIMPLIFY ke \
"Sederhanakan", "Hilangkan pengulangan terbukti", atau "Perjelas kewenangan"; AUTOMATE ke \
"Perbaiki alat/dukungan"; TRANSFER ke "Alihkan tugas bersyarat". "Uji terbatas" boleh dipakai \
untuk jenis apa pun bila opsi itu diusulkan sebagai uji coba. Bila tidak ada padanan yang \
jelas, isi opsi_aplikasi dengan null.
2. Jangan menghitung FTE, jumlah orang, jam kerja, atau formasi, dan jangan menulis angka FTE \
dalam bentuk apa pun. Tidak ada kuantitas terverifikasi pada sumber; parameter kuantitatif \
yang diperlukan ditulis pada unknown_parameters beserta alasannya.
3. Jangan memberi status VERIFIED, READY, atau APPROVE, dan jangan menyatakan opsi disetujui \
atau siap dijalankan. Penetapan opsi tetap keputusan manusia.
4. Jangan menyetujui atau menganjurkan pengalihan tugas hanya karena slot jabatan penerima \
tampak kosong atau longgar; kesanggupan penerima harus didukung sumber.
5. Penerima selain satu jabatan yang tercatat pada sumber alternatif tidak diketahui: tulis \
sebagai unknown_parameters, jangan ditebak.
6. Tiap fakta_sumber menunjuk minimal satu source_id pendukung; hal yang tidak didukung \
sumber ditulis sebagai asumsi (pada opsi atau scenario_assumptions), bukan sebagai fakta.
7. unknown_parameters wajib berisi minimal satu parameter. risks dan checks menunjuk opsi \
lewat opsi_ke (indeks berbasis nol pada options).
8. Gunakan hanya source_id yang ada pada sumber; jangan memakai pengetahuan lain. Parameter \
masalah_id, periode, dan versi_syarat_f4 hanya kode konteks, bukan sumber fakta. Tulis seluruh \
keluaran dalam bahasa Indonesia.\
"""

SKEMA_ISI_P06: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["options", "scenario_assumptions", "unknown_parameters", "risks", "checks"],
    "properties": {
        "options": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["jenis", "opsi_aplikasi", "uraian", "fakta_sumber", "asumsi"],
                "properties": {
                    "jenis": {"type": "string", "enum": list(JENIS_OPSI_P06)},
                    "opsi_aplikasi": {
                        "anyOf": [
                            {"type": "string", "enum": list(OPSI_APLIKASI_P06)},
                            {"type": "null"},
                        ]
                    },
                    "uraian": {"type": "string"},
                    "fakta_sumber": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["pernyataan", "source_ids"],
                            "properties": {
                                "pernyataan": {"type": "string"},
                                "source_ids": {"type": "array", "items": {"type": "string"}},
                            },
                        },
                    },
                    "asumsi": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "scenario_assumptions": {"type": "array", "items": {"type": "string"}},
        "unknown_parameters": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["parameter", "alasan"],
                "properties": {
                    "parameter": {"type": "string"},
                    "alasan": {"type": "string"},
                },
            },
        },
        "risks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["risiko", "opsi_ke"],
                "properties": {
                    "risiko": {"type": "string"},
                    "opsi_ke": {"type": "integer"},
                },
            },
        },
        "checks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["pemeriksaan", "opsi_ke"],
                "properties": {
                    "pemeriksaan": {"type": "string"},
                    "opsi_ke": {"type": "integer"},
                },
            },
        },
    },
}
"""Skema field ``isi`` P06. Satu-satunya field numerik ``opsi_ke`` (indeks opsi); tidak ada field
FTE, skor, maupun status persetujuan. ``unknown_parameters`` memakai ``minItems: 1`` (nilai yang
didukung structured output) karena gerbang F4 mewajibkannya terisi dan Keputusan Desain #124
menuntut skema yang menolak daftar kosong; minimal satu ``source_ids`` per fakta ditagih
``aturan_p06``."""

FUNGSI_P06 = FungsiAi(
    kode="P06",
    prompt_version="p06-1",
    instruksi=INSTRUKSI_P06,
    skema_isi=SKEMA_ISI_P06,
)
"""Definisi fungsi P06 untuk katalog."""


class ParameterP06(BaseModel):
    """Parameter pengajuan P06.

    Hanya kode; tidak ada teks bebas karena ``parameter`` berada di luar gerbang PII.

    Attributes:
        masalah_id: Id ``redesain_masalah`` sasaran (UUID).
        periode: Kode periode konteks; pola ``POLA_PERIODE_AI`` (mis. ``2026/27``).
        versi_syarat_f4: Versi definisi gerbang F4 yang dipakai saat pengajuan; selalu
            ``VERSI_SYARAT_F4``.
        source_verified_quantities: Kuantitas terverifikasi yang dikirim ke model; selalu kosong
            (aplikasi belum punya kuantitas T2-K/FTE terverifikasi), dikunci ``max_length=0``
            sebagai bagian syarat F4 "data kuantitatif sah".
    """

    model_config = ConfigDict(extra="forbid")

    masalah_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=36)
    periode: str = Field(pattern=POLA_PERIODE_AI, max_length=100)
    versi_syarat_f4: Literal["sementara-2026-11"] = VERSI_SYARAT_F4
    source_verified_quantities: list[str] = Field(default_factory=list, max_length=0)


def _string_isi(nilai: Any) -> Iterator[str]:
    """Hasilkan seluruh nilai string di dalam ``nilai`` secara rekursif (kunci tidak ikut)."""
    if isinstance(nilai, str):
        yield nilai
    elif isinstance(nilai, dict):
        for v in nilai.values():
            yield from _string_isi(v)
    elif isinstance(nilai, list):
        for v in nilai:
            yield from _string_isi(v)


def aturan_p06(isi: dict[str, Any], amplop: dict[str, Any]) -> list[str]:
    """Periksa keluaran P06 yang sudah lolos skema (terdaftar di ``ATURAN_ISI``).

    - Setiap ``options[].fakta_sumber[].source_ids`` harus tercantum di
      ``amplop["source_refs"]`` dan tiap daftar minimal satu; bila tidak,
      ``RUJUKAN_TAK_DIKENAL``.
    - Bila ada nilai string isi yang memuat kata utuh ``VERIFIED``, ``READY``, atau ``APPROVE``
      (tak peka huruf), ``STATUS_TERLARANG``.
    - Bila ada nilai string isi yang memuat angka diikuti ``FTE`` (mis. ``1,5 FTE``, ``2FTE``),
      ``ANGKA_FTE``.

    Tiap kode paling banyak sekali, urut seperti di atas, tanpa indeks maupun teks keluaran.
    Daftar tak kosong membuat usulan ``MANUAL``.

    Args:
        isi: Field ``isi`` keluaran.
        amplop: Amplop keluaran (hasil ``_amplop``), memuat ``source_refs``.

    Returns:
        Daftar kode pelanggaran; kosong bila sesuai.

    Example:
        >>> aturan_p06({"options": [], "scenario_assumptions": ["Butuh 1,5 FTE"]}, {})
        ['ANGKA_FTE']
    """
    dikenal = {ref.get("source_id") for ref in amplop.get("source_refs") or []}
    pelanggaran: list[str] = []
    fakta = [
        f
        for opsi in isi.get("options") or []
        if isinstance(opsi, dict)
        for f in opsi.get("fakta_sumber") or []
        if isinstance(f, dict)
    ]
    for f in fakta:
        ids = list(f.get("source_ids") or [])
        if not ids or any(sid not in dikenal for sid in ids):
            pelanggaran.append(KODE_RUJUKAN_TAK_DIKENAL)
            break
    teks = list(_string_isi(isi))
    if any(_RE_STATUS_TERLARANG.search(t) for t in teks):
        pelanggaran.append(KODE_STATUS_TERLARANG)
    if any(_RE_ANGKA_FTE.search(t) for t in teks):
        pelanggaran.append(KODE_ANGKA_FTE)
    return pelanggaran
