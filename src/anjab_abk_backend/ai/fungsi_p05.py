"""Definisi fungsi AI P05: hipotesis proses dan masalah beserta pemeriksaan penyangkalnya.

P05 (library prompt YPII, Process / Issue Hypothesis & Critic, PRM:36-40) membaca satu masalah
redesain yang alur prosesnya sudah terhubung (MX:10) lalu mengusulkan draf alur AS-IS,
hipotesis penyebab, pemeriksaan yang bisa menyangkal tiap hipotesis, dan celah bukti. Sumbernya
dirakit ``rakit_sumber_redesain`` (jenis ``REDESAIN``), termasuk konfirmasi sekolah yang sudah
terkirim (KAI:15).

Hasilnya hanya usulan di ``ai_usulan`` untuk Tim Kajian: draf masalah bukan akar penyebab
terbukti, dan tidak ada kolom hipotesis terstruktur di tabel redesain, jadi pemindahan ke form
masalah/langkah tetap jalur manusia.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .gateway import FungsiAi
from .masukan import POLA_PERIODE_AI

__all__ = [
    "FUNGSI_P05",
    "INSTRUKSI_P05",
    "KODE_HIPOTESIS_TANPA_PENYANGKAL",
    "KODE_RUJUKAN_TAK_DIKENAL",
    "SKEMA_ISI_P05",
    "STATUS_HIPOTESIS_P05",
    "ParameterP05",
    "aturan_p05",
]

STATUS_HIPOTESIS_P05 = "HIPOTESIS"
"""Satu-satunya status hipotesis yang sah: P05 tidak pernah menyatakan penyebab terbukti."""

KODE_RUJUKAN_TAK_DIKENAL = "RUJUKAN_TAK_DIKENAL"
"""Kode pelanggaran: ada ``source_ids`` langkah/hipotesis yang tidak tercantum di
``amplop.source_refs``, atau daftarnya kosong (minimal satu ditagih di sini karena skema
structured output tidak boleh memakai ``minItems``)."""

KODE_HIPOTESIS_TANPA_PENYANGKAL = "HIPOTESIS_TANPA_PENYANGKAL"
"""Kode pelanggaran: ada hipotesis yang tidak ditunjuk satu pun ``disconfirming_checks``."""

INSTRUKSI_P05 = """\
Fungsi: menyusun draf alur proses AS-IS dan hipotesis masalah untuk satu masalah redesain \
sekolah, beserta pemeriksaan yang dapat menyangkal tiap hipotesis dan celah bukti. Sumber \
berpenanda "masalah:" memuat rumusan masalah dan uraian tugas tertaut (task_links); \
"proses:" dan "langkah:" memuat alur yang dicatat Tim; "bukti:" memuat rujukan bukti beserta \
status pemeriksaannya; "koreksi:" memuat koreksi atas langkah; "konfirmasi:" memuat \
konfirmasi sekolah yang sudah terkirim. Orang hanya disebut lewat kode samaran. Hasilnya hanya \
usulan untuk Tim Kajian; bukan keputusan.

Aturan fungsi:
1. Draf masalah tidak sama dengan akar penyebab terbukti. Setiap hipotesis berstatus \
HIPOTESIS; jangan menyatakan atau menyiratkan bahwa penyebab sudah terbukti.
2. Setiap hipotesis wajib punya minimal satu pemeriksaan penyangkal pada \
disconfirming_checks yang menunjuknya lewat hipotesis_ke (indeks berbasis nol pada \
issue_hypotheses), lengkap dengan data yang dibutuhkan untuk menjalankannya.
3. Kemiripan teks antarlangkah atau antarsumber bukan bukti duplikasi. Jangan menggabungkan \
langkah hanya karena kalimatnya mirip.
4. Jangan menetapkan, mengubah, atau menilai status pemeriksaan bukti. Status bukti hanya \
dibaca dari sumber apa adanya.
5. Tiap langkah draf dan tiap hipotesis menunjuk minimal satu source_id pendukung. \
pelaksana berisi jabatan atau peran, bukan nama orang.
6. Hal yang belum didukung sumber ditulis pada evidence_gaps, bukan ditebak.
7. Gunakan hanya source_id yang ada pada sumber; jangan memakai pengetahuan lain. Parameter \
masalah_id dan periode hanya kode konteks, bukan sumber fakta. Tulis seluruh keluaran dalam \
bahasa Indonesia.\
"""

SKEMA_ISI_P05: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["process_draft", "issue_hypotheses", "disconfirming_checks", "evidence_gaps"],
    "properties": {
        "process_draft": {
            "type": "object",
            "additionalProperties": False,
            "required": ["langkah"],
            "properties": {
                "langkah": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["urutan", "uraian", "pelaksana", "source_ids"],
                        "properties": {
                            "urutan": {"type": "integer"},
                            "uraian": {"type": "string"},
                            "pelaksana": {"type": "string"},
                            "source_ids": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                }
            },
        },
        "issue_hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["hipotesis", "status", "source_ids"],
                "properties": {
                    "hipotesis": {"type": "string"},
                    "status": {"type": "string", "const": STATUS_HIPOTESIS_P05},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "disconfirming_checks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["hipotesis_ke", "pemeriksaan", "data_dibutuhkan"],
                "properties": {
                    "hipotesis_ke": {"type": "integer"},
                    "pemeriksaan": {"type": "string"},
                    "data_dibutuhkan": {"type": "string"},
                },
            },
        },
        "evidence_gaps": {"type": "array", "items": {"type": "string"}},
    },
}
"""Skema field ``isi`` P05. ``status`` hipotesis dikunci ``const``; tanpa ``minItems``/
``minLength`` (minimal satu ``source_ids`` dan satu penyangkal per hipotesis ditagih
``aturan_p05``)."""

FUNGSI_P05 = FungsiAi(
    kode="P05",
    prompt_version="p05-1",
    instruksi=INSTRUKSI_P05,
    skema_isi=SKEMA_ISI_P05,
)
"""Definisi fungsi P05 untuk katalog."""


class ParameterP05(BaseModel):
    """Parameter pengajuan P05.

    Hanya kode; tidak ada teks bebas karena ``parameter`` berada di luar gerbang PII.

    Attributes:
        masalah_id: Id ``redesain_masalah`` sasaran (UUID).
        periode: Kode periode konteks; pola ``POLA_PERIODE_AI`` (mis. ``2026/27``).
    """

    model_config = ConfigDict(extra="forbid")

    masalah_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=36)
    periode: str = Field(pattern=POLA_PERIODE_AI, max_length=100)


def aturan_p05(isi: dict[str, Any], amplop: dict[str, Any]) -> list[str]:
    """Periksa keluaran P05 yang sudah lolos skema (terdaftar di ``ATURAN_ISI``).

    - Setiap ``source_ids`` pada ``process_draft.langkah`` dan ``issue_hypotheses`` harus
      tercantum di ``amplop["source_refs"]``, dan tiap daftar minimal satu; bila tidak,
      ``RUJUKAN_TAK_DIKENAL``.
    - Setiap hipotesis (indeks ``i`` pada ``issue_hypotheses``) harus ditunjuk minimal satu
      ``disconfirming_checks`` ber-``hipotesis_ke == i``; bila tidak,
      ``HIPOTESIS_TANPA_PENYANGKAL``.

    Tiap kode paling banyak sekali, tanpa indeks maupun teks keluaran. Daftar tak kosong membuat
    usulan ``MANUAL``.

    Args:
        isi: Field ``isi`` keluaran.
        amplop: Amplop keluaran (hasil ``_amplop``), memuat ``source_refs``.

    Returns:
        Daftar kode pelanggaran; kosong bila sesuai.
    """
    dikenal = {ref.get("source_id") for ref in amplop.get("source_refs") or []}
    langkah = (isi.get("process_draft") or {}).get("langkah") or []
    hipotesis = isi.get("issue_hypotheses") or []
    pelanggaran: list[str] = []
    for elemen in [*langkah, *hipotesis]:
        ids = list(elemen.get("source_ids") or [])
        if not ids or any(sid not in dikenal for sid in ids):
            pelanggaran.append(KODE_RUJUKAN_TAK_DIKENAL)
            break
    ditunjuk = {
        c.get("hipotesis_ke") for c in isi.get("disconfirming_checks") or [] if isinstance(c, dict)
    }
    if any(i not in ditunjuk for i in range(len(hipotesis))):
        pelanggaran.append(KODE_HIPOTESIS_TANPA_PENYANGKAL)
    return pelanggaran
