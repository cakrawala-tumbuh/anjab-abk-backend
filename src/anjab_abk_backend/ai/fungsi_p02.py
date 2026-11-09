"""Definisi fungsi AI P02: normalisasi uraian tugas katalog menjadi kandidat tugas baku.

P02 membaca baris katalog Task Inventory satu jabatan (``ti_uraian_tugas_jabatan``) dan,
opsional, dokumen ``narasi_sumber``, lalu mengusulkan kandidat tugas berbentuk
tindakan-objek-tujuan-cara-output beserta audit tingkat (duty/task/activity), dugaan duplikasi,
dan alasan pecah/gabung. Hasilnya hanya usulan untuk Tim Kajian: kandidat bukan pekerjaan aktual
yang tervalidasi (MX:8), narasi asal tidak diubah, dan promosi kandidat ke katalog tetap jalur
manusia. Fungsi ini tidak menulis katalog.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .gateway import FungsiAi
from .masukan import POLA_PERIODE_AI
from .redaksi import SumberAi

__all__ = [
    "AWALAN_SUMBER_URAIAN",
    "FUNGSI_P02",
    "INSTRUKSI_P02",
    "JENIS_SUMBER_KATALOG_TI",
    "KODE_RUJUKAN_KURANG",
    "KODE_RUJUKAN_TAK_DIKENAL",
    "POLA_KODE_P02",
    "SKEMA_ISI_P02",
    "TINGKAT_TUGAS_P02",
    "ParameterP02",
    "aturan_p02",
    "id_sumber_uraian",
    "sumber_katalog_ti",
    "teks_sumber_katalog_ti",
]

JENIS_SUMBER_KATALOG_TI = "KATALOG_TI"
"""Jenis sumber baris katalog Task Inventory. Baru boleh dikirim ke model bila operator
mencantumkannya di ``AI_JENIS_SUMBER_DIIZINKAN`` (keputusan aktivasi, bukan bawaan)."""

AWALAN_SUMBER_URAIAN = "uraian:"
"""Awalan ``source_id`` baris katalog: ``uraian:<ti_uraian_tugas.id>``."""

TINGKAT_TUGAS_P02 = ("DUTY", "TASK", "ACTIVITY")
"""Tingkat audit kandidat tugas yang sah."""

JENIS_PECAH_GABUNG_P02 = ("PECAH", "GABUNG")
"""Jenis alasan pada ``split_merge_rationale``."""

POLA_KODE_P02 = r"^[A-Za-z0-9_.:-]+$"
"""Pola kode parameter dan ``unit``: tanpa spasi, tanpa teks bebas."""

KODE_RUJUKAN_TAK_DIKENAL = "RUJUKAN_TAK_DIKENAL"
"""Kode pelanggaran: ada ``source_ids`` yang tidak tercantum di ``amplop.source_refs``."""

KODE_RUJUKAN_KURANG = "RUJUKAN_KURANG"
"""Kode pelanggaran: ``source_ids`` kurang dari batas minimum (kandidat dan pecah/gabung >= 1,
dugaan duplikasi >= 2). Ditegakkan di sini karena skema structured output tidak boleh memakai
``minItems`` (lihat ``skema_dengan_amplop``)."""

_FIELD_TEKS_KATALOG = ("kode", "unit", "tugas_pokok", "detil_tugas", "uraian")
_FIELD_STANDAR_KATALOG = (
    "std_sumber_bukti",
    "std_kondisi",
    "std_frekuensi_teks",
    "std_durasi_per_kali",
    "std_jam_per_minggu",
    "std_peak4w_hours",
    "std_va_type",
    "std_opm_importance",
    "std_opm_frequency",
    "std_opm_criticality",
)
FIELD_SUMBER_KATALOG_TI = (*_FIELD_TEKS_KATALOG, *_FIELD_STANDAR_KATALOG)
"""Satu-satunya kunci yang boleh muncul pada teks sumber ``KATALOG_TI`` (tugas dan standar)."""

INSTRUKSI_P02 = """\
Fungsi: menormalkan uraian tugas katalog satu jabatan menjadi kandidat tugas baku untuk Tim \
Kajian. Sumber berpenanda "uraian:" adalah baris katalog; sumber lainnya adalah dokumen \
pendukung. Hasilnya hanya usulan; bukan keputusan dan bukan perubahan katalog.

Aturan fungsi:
1. Kandidat tugas bukan pekerjaan aktual yang tervalidasi. Jangan menyatakan atau menyiratkan \
bahwa tugas itu sudah atau sedang dikerjakan pemangku jabatan.
2. Narasi asal tidak diubah: jangan menulis ulang baris katalog sebagai fakta baru. Tiap \
kandidat merumuskan tindakan, objek, tujuan, cara, dan output, dan menunjuk minimal satu \
source_id baris yang menjadi dasarnya.
3. Tandai tingkat tiap kandidat: DUTY (tanggung jawab besar), TASK (unit kerja dengan output \
jelas), atau ACTIVITY (langkah di dalam tugas).
4. Kemiripan teks bukan bukti duplikasi. Catat dugaan duplikasi pada duplicate_suspicions \
dengan minimal dua source_id dan alasannya; jangan menggabungkan diam-diam.
5. Usulan pecah atau gabung masuk split_merge_rationale (jenis PECAH atau GABUNG) dengan \
source_id dan alasannya.
6. Hal yang perlu dipastikan manusia masuk reviewer_questions. Jangan mengisi persetujuan, skor, \
atau keputusan.
7. Gunakan hanya source_id yang ada pada sumber; jangan memakai pengetahuan lain dan jangan \
mengarang angka. Parameter jabatan_kode, unit, dan periode hanya kode konteks, bukan sumber \
fakta. Tulis seluruh keluaran dalam bahasa Indonesia.\
"""

_SOURCE_IDS = {"type": "array", "items": {"type": "string"}}

SKEMA_ISI_P02: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "task_candidates",
        "duplicate_suspicions",
        "split_merge_rationale",
        "reviewer_questions",
    ],
    "properties": {
        "task_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "tindakan",
                    "objek",
                    "tujuan",
                    "cara",
                    "output",
                    "tingkat",
                    "source_ids",
                ],  # fmt: skip
                "properties": {
                    "tindakan": {"type": "string"},
                    "objek": {"type": "string"},
                    "tujuan": {"type": "string"},
                    "cara": {"type": "string"},
                    "output": {"type": "string"},
                    "tingkat": {"type": "string", "enum": list(TINGKAT_TUGAS_P02)},
                    "source_ids": _SOURCE_IDS,
                },
            },
        },
        "duplicate_suspicions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source_ids", "alasan"],
                "properties": {"source_ids": _SOURCE_IDS, "alasan": {"type": "string"}},
            },
        },
        "split_merge_rationale": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["jenis", "source_ids", "alasan"],
                "properties": {
                    "jenis": {"type": "string", "enum": list(JENIS_PECAH_GABUNG_P02)},
                    "source_ids": _SOURCE_IDS,
                    "alasan": {"type": "string"},
                },
            },
        },
        "reviewer_questions": {"type": "array", "items": {"type": "string"}},
    },
}
"""Skema field ``isi`` P02: tanpa ``if/then``, ``minLength``, ``minItems``, dan tanpa field
persetujuan, skor, atau keputusan. Jumlah minimum ``source_ids`` ditagih ``aturan_p02``."""

FUNGSI_P02 = FungsiAi(
    kode="P02",
    prompt_version="p02-1",
    instruksi=INSTRUKSI_P02,
    skema_isi=SKEMA_ISI_P02,
)
"""Definisi fungsi P02 untuk katalog."""


class ParameterP02(BaseModel):
    """Parameter pengajuan P02.

    Hanya kode; tidak ada teks bebas karena ``parameter`` berada di luar gerbang PII.

    Attributes:
        jabatan_kode: Kode jabatan sasaran (``jabatan.kode``).
        unit: Kode unit katalog yang dipersempit, atau ``None`` untuk seluruh unit.
        periode: Kode periode konteks; pola ``POLA_PERIODE_AI`` (mis. ``2026/27``).
    """

    model_config = ConfigDict(extra="forbid")

    jabatan_kode: str = Field(pattern=POLA_KODE_P02, max_length=30)
    unit: str | None = Field(default=None, pattern=POLA_KODE_P02, max_length=20)
    periode: str = Field(pattern=POLA_PERIODE_AI, max_length=100)


def id_sumber_uraian(uraian_tugas_id: str) -> str:
    """Bentuk ``source_id`` satu baris katalog.

    Args:
        uraian_tugas_id: Id ``ti_uraian_tugas`` (unik per jabatan pada tabel tautan).

    Returns:
        ``uraian:<uraian_tugas_id>``.
    """
    return f"{AWALAN_SUMBER_URAIAN}{uraian_tugas_id}"


def teks_sumber_katalog_ti(nilai: dict[str, Any]) -> str:
    """Susun teks sumber ``KATALOG_TI`` dari field tugas dan standar satu baris katalog.

    Hanya kunci di ``FIELD_SUMBER_KATALOG_TI`` yang dipakai, dalam urutan tetap, satu baris
    ``kunci: nilai`` per field; nilai ``None`` atau string kosong dilewati. Kunci lain pada
    ``nilai`` (mis. ``jabatan_id``, ``urutan``) diabaikan sehingga tidak pernah ikut terkirim.

    Args:
        nilai: Pemetaan nama field ke nilai baris katalog.

    Returns:
        Teks deterministik untuk baris itu.
    """
    baris = []
    for kunci in FIELD_SUMBER_KATALOG_TI:
        isi = nilai.get(kunci)
        if isi is None or (isinstance(isi, str) and not isi.strip()):
            continue
        baris.append(f"{kunci}: {' '.join(str(isi).split())}")
    return "\n".join(baris)


def sumber_katalog_ti(uraian_tugas_id: str, nilai: dict[str, Any]) -> SumberAi:
    """Bungkus satu baris katalog sebagai ``SumberAi`` berjenis ``KATALOG_TI``.

    Args:
        uraian_tugas_id: Id ``ti_uraian_tugas`` baris itu.
        nilai: Field baris katalog (lihat ``teks_sumber_katalog_ti``).

    Returns:
        Sumber dengan ``source_id`` ``uraian:<id>`` dan ``source_hash`` SHA-256 teksnya.
    """
    teks = teks_sumber_katalog_ti(nilai)
    return SumberAi(
        source_id=id_sumber_uraian(uraian_tugas_id),
        source_hash=hashlib.sha256(teks.encode("utf-8")).hexdigest(),
        jenis=JENIS_SUMBER_KATALOG_TI,
        teks=teks,
    )


def aturan_p02(isi: dict[str, Any], amplop: dict[str, Any]) -> list[str]:
    """Periksa keluaran P02 yang sudah lolos skema (terdaftar di ``ATURAN_ISI``).

    Setiap ``source_ids`` pada ``task_candidates``, ``duplicate_suspicions``, dan
    ``split_merge_rationale`` harus tercantum di ``amplop["source_refs"]`` (yang sudah dicocokkan
    dengan sumber masukan oleh ``cek_keluaran``); bila tidak, ``RUJUKAN_TAK_DIKENAL``. Kandidat
    dan pecah/gabung minimal satu ``source_ids``, dugaan duplikasi minimal dua (``source_id``
    berbeda); bila kurang, ``RUJUKAN_KURANG``. Tiap kode paling banyak sekali, tanpa indeks
    maupun teks keluaran.

    Args:
        isi: Field ``isi`` keluaran.
        amplop: Amplop keluaran (hasil ``_amplop``), memuat ``source_refs``.

    Returns:
        Daftar kode pelanggaran; kosong bila sesuai.
    """
    dikenal = {ref.get("source_id") for ref in amplop.get("source_refs") or []}
    minimum = (
        ("task_candidates", 1),
        ("duplicate_suspicions", 2),
        ("split_merge_rationale", 1),
    )
    pelanggaran: list[str] = []
    for kunci, batas in minimum:
        for elemen in isi.get(kunci) or []:
            ids = list(elemen.get("source_ids") or [])
            if any(sid not in dikenal for sid in ids):
                if KODE_RUJUKAN_TAK_DIKENAL not in pelanggaran:
                    pelanggaran.append(KODE_RUJUKAN_TAK_DIKENAL)
            if len(set(ids)) < batas and KODE_RUJUKAN_KURANG not in pelanggaran:
                pelanggaran.append(KODE_RUJUKAN_KURANG)
    return pelanggaran
