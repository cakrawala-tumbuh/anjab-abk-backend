"""Definisi fungsi AI P09: kritik AI atas satu versi narasi (pembantu reviewer).

P09 mencari klaim tanpa dasar, asumsi tersembunyi, dan risiko privasi pada draf narasi.
Hasilnya hanya usulan untuk reviewer manusia: bukan bukti, bukan tinjauan, dan bukan
persetujuan. Model yang sama yang menulis draf bukan pemeriksa independen, jadi keluaran ini
tidak pernah dihitung sebagai pemeriksaan kedua.

Draf ikut dikirim sebagai sumber berpenanda ``versi:<id>`` agar melewati gerbang PII dan
dapat dikutip (``cited_spans``); penanda itu bukan baris ``narasi_sumber``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .gateway import FungsiAi

__all__ = [
    "AWALAN_SUMBER_VERSI",
    "FUNGSI_P09",
    "INSTRUKSI_P09",
    "KATEGORI_TEMUAN_P09",
    "PERAN_P09",
    "SKEMA_ISI_P09",
    "ParameterP09",
    "id_sumber_versi",
]

PERAN_P09 = "REVIEWER_OTOMATIS_PEMBANTU"
"""Nilai tetap ``peran`` pada keluaran; skema memakai ``const``."""

AWALAN_SUMBER_VERSI = "versi:"
"""Awalan ``source_id`` untuk draf yang dikirim sebagai sumber."""

KATEGORI_TEMUAN_P09 = (
    "KLAIM_TANPA_DASAR",
    "ASUMSI_TERSEMBUNYI",
    "BIAS_PROMPT",
    "PRIVASI",
    "SALAH_TAUTAN",
    "PENGHILANGAN",
    "KONFLIK_METODE",
)
"""Kategori temuan yang sah."""

_POLA_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

INSTRUKSI_P09 = """\
Fungsi: mengkritik satu draf narasi sebagai pembantu reviewer manusia. Sumber yang \
berpenanda "versi:" adalah draf yang dikritik; sumber lainnya adalah bahan yang menjadi dasarnya.

Aturan fungsi:
1. Jangan menyetujui draf, jangan menyatakan draf layak, dan jangan memberi skor atau \
keputusan. Hanya manusia yang menyetujui.
2. Buat temuan hanya atas draf dan sumber yang diberikan; jangan memakai pengetahuan lain.
3. Kemiripan bukan bukti: kata yang mirip antara draf dan sumber tidak membuktikan klaim.
4. Jangan menyatakan skor WCP atau DCS sah atau terbukti; skor dari instrumen itu bukan \
bukti atas klaim narasi.
5. Dua persetujuan bukan dua bukti independen: persetujuan ganda atas satu bahan tidak \
menambah bukti.
6. Jangan menghapus atau menyarankan penghapusan kontrol wajib, pemeriksaan, atau tinjauan manusia.
7. Kelompokkan temuan: blocking_findings untuk yang harus diperbaiki sebelum draf diteruskan, \
major_findings untuk yang penting. Tiap temuan memuat kategori, source_id, dan span persis \
dari sumber itu. Usulan perbaikan masuk correction_proposals; hal yang tidak dapat Anda \
periksa masuk limitations.
8. Tanpa temuan pun Anda wajib mengutip minimal satu span yang Anda periksa pada cited_spans, \
dan blocking_findings serta major_findings boleh berupa daftar kosong.
9. Isi peran dengan REVIEWER_OTOMATIS_PEMBANTU. Tulis seluruh keluaran dalam bahasa Indonesia.\
"""

_TEMUAN = {
    "type": "object",
    "additionalProperties": False,
    "required": ["temuan", "kategori", "source_id", "span"],
    "properties": {
        "temuan": {"type": "string"},
        "kategori": {"type": "string", "enum": list(KATEGORI_TEMUAN_P09)},
        "source_id": {"type": "string"},
        "span": {"type": "string"},
    },
}

SKEMA_ISI_P09: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "peran",
        "blocking_findings",
        "major_findings",
        "correction_proposals",
        "limitations",
    ],
    "properties": {
        "peran": {"type": "string", "const": PERAN_P09},
        "blocking_findings": {"type": "array", "items": _TEMUAN},
        "major_findings": {"type": "array", "items": _TEMUAN},
        "correction_proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["span", "usulan", "alasan"],
                "properties": {
                    "span": {"type": "string"},
                    "usulan": {"type": "string"},
                    "alasan": {"type": "string"},
                },
            },
        },
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
}
"""Skema field ``isi`` P09: tanpa ``if/then``, ``minLength``, ``minItems``, dan tanpa field
persetujuan, skor, atau keputusan."""

FUNGSI_P09 = FungsiAi(
    kode="P09",
    prompt_version="p09-1",
    instruksi=INSTRUKSI_P09,
    skema_isi=SKEMA_ISI_P09,
)
"""Definisi fungsi P09 untuk katalog."""


def id_sumber_versi(narasi_versi_id: str) -> str:
    """Bentuk ``source_id`` draf yang dikirim sebagai sumber.

    Args:
        narasi_versi_id: Id versi narasi yang dikritik.

    Returns:
        ``versi:<id>``.
    """
    return f"{AWALAN_SUMBER_VERSI}{narasi_versi_id}"


class ParameterP09(BaseModel):
    """Parameter pengajuan P09.

    Hanya satu id berpola UUID; tidak ada teks bebas karena ``parameter`` berada di luar
    gerbang PII (draf dikirim sebagai sumber, bukan parameter).

    Attributes:
        narasi_versi_id: Id versi narasi yang dikritik.
    """

    model_config = ConfigDict(extra="forbid")

    narasi_versi_id: str = Field(pattern=_POLA_UUID, max_length=36)
