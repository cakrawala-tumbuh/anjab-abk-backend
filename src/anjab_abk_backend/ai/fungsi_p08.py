"""Definisi fungsi AI P08: sintesis bukti riset atas protokol terkunci dan statistik terverifikasi.

P08 (library prompt YPII, Scientific Evidence Synthesizer, PRM:54-58) menyusun draf deskripsi
metode dan hasil yang dapat direplikasi, tabel bukti, keterbatasan, dan daftar klaim yang tidak
didukung. P08 dilarang menyatakan signifikansi, non-inferioritas, atau peringkat jurnal (Q1)
tanpa keluaran analisis tervalidasi; F5 (KAI:17) mensyaratkan protokol versi terkunci dan
statistik yang dihasilkan kode.

Pengajuan hanya sah untuk protokol ``TERKUNCI`` yang punya minimal satu statistik
``TERVERIFIKASI``. Sumbernya dirakit ``rakit_sumber_riset`` (``ai/sumber_riset.py``, jenis
``RISET``); statistik ``DRAF`` tidak pernah dikirim. Fungsi ini nonaktif bawaan (Keputusan Tim
4 November menahan AI F5, KTK:192, dan OD-09 belum terkunci); hasilnya hanya usulan di
``ai_usulan``.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from ..schemas.riset_protokol import POLA_KODE_PROTOKOL
from .gateway import FungsiAi
from .masukan import POLA_PERIODE_AI

__all__ = [
    "AWALAN_STATISTIK",
    "BAGIAN_P08",
    "FUNGSI_P08",
    "INSTRUKSI_P08",
    "KODE_HASIL_TANPA_STATISTIK",
    "KODE_KLAIM_TANPA_STATISTIK",
    "KODE_KLAIM_TERLARANG",
    "KODE_RUJUKAN_TAK_DIKENAL",
    "SKEMA_ISI_P08",
    "ParameterP08",
    "aturan_p08",
]

BAGIAN_P08 = ("METODE", "HASIL")
"""Bagian naskah yang boleh disusun P08."""

AWALAN_STATISTIK = "statistik:"
"""Awalan ``source_id`` statistik terverifikasi; satu-satunya rujukan sah untuk klaim hasil."""

KODE_RUJUKAN_TAK_DIKENAL = "RUJUKAN_TAK_DIKENAL"
"""Kode pelanggaran: ada ``source_ids`` atau ``statistik_ids`` yang tidak tercantum di
``amplop.source_refs``, atau ``manuscript_sections[].source_ids`` kosong (minimal satu ditagih di
sini karena konvensi skema repo tidak memakai ``minItems`` untuk field ini)."""

KODE_KLAIM_TANPA_STATISTIK = "KLAIM_TANPA_STATISTIK"
"""Kode pelanggaran: ada ``evidence_table[].statistik_ids`` tanpa awalan ``statistik:``, atau
daftarnya kosong."""

KODE_HASIL_TANPA_STATISTIK = "HASIL_TANPA_STATISTIK"
"""Kode pelanggaran: ada bagian ``HASIL`` yang tidak merujuk satu pun sumber ``statistik:``."""

KODE_KLAIM_TERLARANG = "KLAIM_TERLARANG"
"""Kode pelanggaran: teks naskah atau tabel bukti memuat kata utuh ``Q1``, atau bagian tanpa
sumber ``statistik:`` memuat ``signifikan``/``non-inferior`` (tak peka huruf)."""

_RE_Q1 = re.compile(r"\bQ1\b")
_RE_SIGNIFIKAN = re.compile(r"signifikan|non[- ]?inferior", re.IGNORECASE)

INSTRUKSI_P08 = """\
Fungsi: menyusun draf sintesis bukti riset untuk satu protokol riset yang sudah terkunci. Sumber \
berpenanda "protokol:" memuat protokol versi terkunci (kode, versi, isi_hash, isi); \
"statistik:" memuat keluaran analisis yang sudah diverifikasi pihak independen (nama analisis, \
rujukan kode sumber, keluaran); "kasus-negatif:" memuat kasus yang tidak mendukung atau \
berlawanan dengan dugaan; "versi-metode:" memuat log versi metode. Hasilnya hanya usulan untuk \
Tim Kajian; bukan naskah final.

Aturan fungsi:
1. Jangan mengarang statistik, angka, referensi pustaka, atau bukti manfaat. Setiap angka hasil \
harus tercantum pada sumber "statistik:".
2. manuscript_sections berisi bagian METODE atau HASIL; tiap bagian menunjuk minimal satu \
source_id pendukung. Bagian HASIL wajib menunjuk minimal satu sumber "statistik:".
3. evidence_table: tiap klaim menunjuk minimal satu statistik lewat statistik_ids berawalan \
"statistik:" dan menyebut batasannya.
4. Jangan menyatakan signifikan, signifikansi, atau non-inferior kecuali bagian itu menunjuk \
sumber "statistik:" yang memuatnya. Jangan pernah menyebut peringkat jurnal (Q1) atau kelayakan \
terbit.
5. Kasus negatif wajib disebut: ringkas tiap sumber "kasus-negatif:" pada bagian HASIL atau \
limitations.
6. Klaim yang tidak didukung statistik terverifikasi masuk unsupported_claims beserta alasannya, \
bukan ke naskah. limitations wajib berisi minimal satu keterbatasan.
7. Gunakan hanya source_id yang ada pada sumber; jangan memakai pengetahuan lain. Parameter \
protokol_kode, protokol_versi, dan periode hanya kode konteks, bukan sumber fakta. Tulis \
seluruh keluaran dalam bahasa Indonesia.\
"""

SKEMA_ISI_P08: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "manuscript_sections",
        "evidence_table",
        "limitations",
        "unsupported_claims",
    ],
    "properties": {
        "manuscript_sections": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["bagian", "teks", "source_ids"],
                "properties": {
                    "bagian": {"type": "string", "enum": list(BAGIAN_P08)},
                    "teks": {"type": "string"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "evidence_table": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["klaim", "statistik_ids", "batasan"],
                "properties": {
                    "klaim": {"type": "string"},
                    "statistik_ids": {"type": "array", "items": {"type": "string"}},
                    "batasan": {"type": "string"},
                },
            },
        },
        "limitations": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "unsupported_claims": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["klaim", "alasan"],
                "properties": {
                    "klaim": {"type": "string"},
                    "alasan": {"type": "string"},
                },
            },
        },
    },
}
"""Skema field ``isi`` P08. Tanpa field numerik, skor, maupun status persetujuan.
``limitations`` memakai ``minItems: 1`` (nilai yang didukung structured output) karena Skenario
Uji #126 menuntut skema menolak daftar kosong; minimal satu ``source_ids`` per bagian dan satu
``statistik_ids`` per klaim ditagih ``aturan_p08``."""

FUNGSI_P08 = FungsiAi(
    kode="P08",
    prompt_version="p08-1",
    instruksi=INSTRUKSI_P08,
    skema_isi=SKEMA_ISI_P08,
)
"""Definisi fungsi P08 untuk katalog."""


class ParameterP08(BaseModel):
    """Parameter pengajuan P08.

    Hanya kode; tidak ada teks bebas karena ``parameter`` berada di luar gerbang PII.

    Attributes:
        protokol_kode: Kode protokol riset sasaran (pola ``POLA_KODE_PROTOKOL``).
        protokol_versi: Versi protokol per kode, mulai 1.
        periode: Kode periode konteks; pola ``POLA_PERIODE_AI`` (mis. ``2026/27``).
    """

    model_config = ConfigDict(extra="forbid")

    protokol_kode: str = Field(pattern=POLA_KODE_PROTOKOL, max_length=40)
    protokol_versi: int = Field(ge=1)
    periode: str = Field(pattern=POLA_PERIODE_AI, max_length=100)


def _daftar_dict(nilai: Any) -> list[dict[str, Any]]:
    """Kembalikan elemen dict dari ``nilai`` bila berupa list; selain itu daftar kosong."""
    return [x for x in nilai if isinstance(x, dict)] if isinstance(nilai, list) else []


def _ids(nilai: Any) -> list[str]:
    """Kembalikan ``nilai`` sebagai daftar string bila berupa list; selain itu daftar kosong."""
    return [str(x) for x in nilai] if isinstance(nilai, list) else []


def aturan_p08(isi: dict[str, Any], amplop: dict[str, Any]) -> list[str]:
    """Periksa keluaran P08 yang sudah lolos skema (terdaftar di ``ATURAN_ISI``).

    - ``RUJUKAN_TAK_DIKENAL``: ada ``manuscript_sections[].source_ids`` atau
      ``evidence_table[].statistik_ids`` yang tidak tercantum di ``amplop["source_refs"]``, atau
      ``source_ids`` sebuah bagian kosong.
    - ``KLAIM_TANPA_STATISTIK``: ada ``statistik_ids`` tanpa awalan ``statistik:``, atau daftar
      ``statistik_ids`` sebuah klaim kosong.
    - ``HASIL_TANPA_STATISTIK``: ada bagian ``HASIL`` yang tidak merujuk satu pun ``statistik:``.
    - ``KLAIM_TERLARANG``: ``teks`` bagian, ``klaim``, atau ``batasan`` tabel bukti memuat kata
      utuh ``Q1``; atau ``teks`` bagian tanpa sumber ``statistik:`` memuat ``signifikan`` atau
      ``non-inferior`` (tak peka huruf). ``unsupported_claims`` dan ``limitations`` tidak
      diperiksa karena di sanalah klaim yang tidak didukung memang ditulis.

    Tiap kode paling banyak sekali, urut seperti di atas, tanpa indeks maupun teks keluaran.
    Daftar tak kosong membuat usulan ``MANUAL``.

    Args:
        isi: Field ``isi`` keluaran.
        amplop: Amplop keluaran (hasil ``_amplop``), memuat ``source_refs``.

    Returns:
        Daftar kode pelanggaran; kosong bila sesuai.

    Example:
        >>> isi = {"manuscript_sections": [
        ...     {"bagian": "HASIL", "teks": "Terbit di jurnal Q1", "source_ids": ["protokol:p"]}
        ... ], "evidence_table": []}
        >>> aturan_p08(isi, {"source_refs": [{"source_id": "protokol:p"}]})
        ['HASIL_TANPA_STATISTIK', 'KLAIM_TERLARANG']
    """
    dikenal = {ref.get("source_id") for ref in amplop.get("source_refs") or []}
    bagian = _daftar_dict(isi.get("manuscript_sections"))
    klaim = _daftar_dict(isi.get("evidence_table"))
    ids_bagian = [_ids(b.get("source_ids")) for b in bagian]
    ids_klaim = [_ids(k.get("statistik_ids")) for k in klaim]

    rujukan_asing = any(not ids for ids in ids_bagian) or any(
        sid not in dikenal for ids in (*ids_bagian, *ids_klaim) for sid in ids
    )
    tanpa_statistik = any(
        not ids or any(not sid.startswith(AWALAN_STATISTIK) for sid in ids) for ids in ids_klaim
    )
    ada_statistik = [any(sid.startswith(AWALAN_STATISTIK) for sid in ids) for ids in ids_bagian]
    hasil_tanpa = any(
        b.get("bagian") == "HASIL" and not stat
        for b, stat in zip(bagian, ada_statistik, strict=True)
    )
    teks_q1 = [str(b.get("teks") or "") for b in bagian] + [
        str(k.get(f) or "") for k in klaim for f in ("klaim", "batasan")
    ]
    terlarang = any(_RE_Q1.search(t) for t in teks_q1) or any(
        not stat and _RE_SIGNIFIKAN.search(str(b.get("teks") or ""))
        for b, stat in zip(bagian, ada_statistik, strict=True)
    )

    pelanggaran: list[str] = []
    for kena, kode in (
        (rujukan_asing, KODE_RUJUKAN_TAK_DIKENAL),
        (tanpa_statistik, KODE_KLAIM_TANPA_STATISTIK),
        (hasil_tanpa, KODE_HASIL_TANPA_STATISTIK),
        (terlarang, KODE_KLAIM_TERLARANG),
    ):
        if kena:
            pelanggaran.append(kode)
    return pelanggaran
