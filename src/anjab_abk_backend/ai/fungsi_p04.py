"""Definisi fungsi AI P04: pengusul satu pertanyaan bukti netral, tanpa pengiriman.

Saat bukti atas satu klaim kurang, P04 menilai apakah kekurangan itu material, yaitu mengubah
keputusan terkait. Hanya bila material, ia mengusulkan SATU pertanyaan netral untuk Tim Kajian.
Hasilnya hanya usulan: tidak dikirim ke siapa pun, tidak membuat permintaan bukti, dan reviewer
manusia yang memutuskan (R11-008).

``klaim`` dan ``keputusan_terkait`` adalah teks bebas dari klien, jadi keduanya dikirim sebagai
sumber (``klaim:<uuid>`` dan ``keputusan:<uuid>``) agar melewati gerbang PII; penanda itu bukan
baris ``narasi_sumber``.

Status keluaran: kekurangan bukti atas klaim adalah objek penilaian P04, jadi ``AI_DRAFT``
dipakai selama ada kutipan yang menopang penilaian (juga saat ``material`` true); ``EVIDENCE_GAP``
hanya bila tidak ada span yang dapat dikutip. Aturan ini ada di ``INSTRUKSI_P04`` (``p04-2``)
karena guardrail bersama memerintahkan ``EVIDENCE_GAP`` setiap kali rujukan pendukung tidak ada.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .gateway import FungsiAi
from .masukan import POLA_PERIODE_AI

__all__ = [
    "AWALAN_SUMBER_KEPUTUSAN",
    "AWALAN_SUMBER_KLAIM",
    "FUNGSI_P04",
    "INSTRUKSI_P04",
    "KODE_ATURAN_P04_DILANGGAR",
    "KODE_LEBIH_DARI_SATU_PERTANYAAN",
    "SKEMA_ISI_P04",
    "ParameterP04",
    "aturan_p04",
    "id_sumber_keputusan",
    "id_sumber_klaim",
]

AWALAN_SUMBER_KLAIM = "klaim:"
"""Awalan ``source_id`` untuk teks klaim yang dikirim sebagai sumber."""

AWALAN_SUMBER_KEPUTUSAN = "keputusan:"
"""Awalan ``source_id`` untuk teks keputusan terkait yang dikirim sebagai sumber."""

KODE_ATURAN_P04_DILANGGAR = "ATURAN_P04_DILANGGAR"
"""Kode ``kode_serap``: ``material`` tidak sejalan dengan ada-tidaknya pertanyaan."""

KODE_LEBIH_DARI_SATU_PERTANYAAN = "LEBIH_DARI_SATU_PERTANYAAN"
"""Kode ``kode_serap``: pertanyaan memuat lebih dari satu tanda tanya."""

_POLA_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
_NAMESPACE_SUMBER = uuid.UUID("5d6f8a52-3c1e-4b0a-9a57-0a4f2d1c7e04")

INSTRUKSI_P04 = """\
Fungsi: menilai apakah kekurangan bukti atas satu klaim mengubah keputusan terkait, dan bila \
ya, mengusulkan satu pertanyaan netral untuk Tim Kajian. Sumber berpenanda "klaim:" adalah klaim \
yang dinilai; sumber berpenanda "keputusan:" adalah keputusan yang bergantung pada klaim itu; \
sumber lainnya adalah materi bukti yang tersedia.

Aturan fungsi:
1. Periksa materi yang ada lebih dulu. Bila sumber sudah menjawab klaim, isi material dengan \
false; one_neutral_question, why_ask, dan preferred_role diisi null.
2. Isi material dengan true hanya bila bukti yang kurang itu dapat mengubah keputusan terkait. \
Tuliskan alasannya pada materiality_rationale. Bila tidak material, pertanyaan tidak diusulkan.
3. Bila material, usulkan tepat satu pertanyaan netral pada one_neutral_question, berupa satu \
kalimat dengan satu tanda tanya, tanpa mengarahkan jawaban dan tanpa mengandaikan jawabannya.
4. Jangan meminta nama murid atau keluarga, dan jangan meminta data pribadi. preferred_role \
berisi jabatan atau peran yang sebaiknya ditanya, bukan nama orang.
5. Jangan mengisi persetujuan, skor, atau keputusan, dan jangan menyatakan klaim benar atau \
salah. Anda hanya mengusulkan; Anda tidak mengirim apa pun kepada siapa pun.
6. Buat penilaian hanya atas sumber yang diberikan; jangan memakai pengetahuan lain. Alternatif \
selain bertanya (misalnya memeriksa dokumen lain) masuk alternatives; hal yang tidak dapat \
Anda periksa masuk limitations.
7. Kutip minimal satu span yang Anda periksa pada cited_spans, persis dari sumbernya. Tulis \
seluruh keluaran dalam bahasa Indonesia.
8. Aturan status. Kekurangan bukti atas klaim adalah objek penilaian fungsi ini, bukan celah \
bukti keluaran. Isi status dengan AI_DRAFT bila penilaian materialitas Anda dapat ditopang \
minimal satu kutipan dari sumber berpenanda "klaim:", sumber berpenanda "keputusan:", atau \
materi bukti, termasuk saat material bernilai true. Isi status dengan EVIDENCE_GAP hanya bila \
tidak ada satu pun span yang dapat Anda kutip dari sumber mana pun.\
"""

_NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}

SKEMA_ISI_P04: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "material",
        "materiality_rationale",
        "one_neutral_question",
        "why_ask",
        "preferred_role",
        "alternatives",
        "limitations",
    ],
    "properties": {
        "material": {"type": "boolean"},
        "materiality_rationale": {"type": "string"},
        "one_neutral_question": _NULLABLE_STRING,
        "why_ask": _NULLABLE_STRING,
        "preferred_role": _NULLABLE_STRING,
        "alternatives": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
}
"""Skema field ``isi`` P04: tanpa ``if/then``, ``minLength``, ``minItems``, tanpa field
persetujuan, skor, atau keputusan. Pertanyaan berupa string tunggal, bukan larik."""

FUNGSI_P04 = FungsiAi(
    kode="P04",
    prompt_version="p04-2",
    instruksi=INSTRUKSI_P04,
    skema_isi=SKEMA_ISI_P04,
)
"""Definisi fungsi P04 untuk katalog."""


def _id_sumber(awalan: str, teks: str) -> str:
    """Bentuk ``source_id`` deterministik ``<awalan><uuid5>`` dari isi teks."""
    return f"{awalan}{uuid.uuid5(_NAMESPACE_SUMBER, awalan + teks)}"


def id_sumber_klaim(klaim: str) -> str:
    """Bentuk ``source_id`` untuk teks klaim yang dikirim sebagai sumber.

    UUID diturunkan (UUID5) dari isi klaim, bukan diundi, sehingga masukan yang sama
    menghasilkan ``source_id`` dan hash masukan run yang sama pada pengajuan ulang.

    Args:
        klaim: Teks klaim.

    Returns:
        ``klaim:<uuid>``.
    """
    return _id_sumber(AWALAN_SUMBER_KLAIM, klaim)


def id_sumber_keputusan(keputusan: str) -> str:
    """Bentuk ``source_id`` untuk teks keputusan terkait yang dikirim sebagai sumber.

    Args:
        keputusan: Teks keputusan terkait.

    Returns:
        ``keputusan:<uuid>`` (UUID5 atas isi teks).
    """
    return _id_sumber(AWALAN_SUMBER_KEPUTUSAN, keputusan)


def aturan_p04(isi: dict[str, Any], amplop: dict[str, Any]) -> list[str]:
    """Periksa keluaran P04 yang sudah lolos skema (terdaftar di ``ATURAN_ISI``).

    ``material=true`` tanpa pertanyaan, atau ``material=false`` dengan pertanyaan, melanggar
    ``ATURAN_P04_DILANGGAR``. Pertanyaan dengan lebih dari satu tanda tanya melanggar
    ``LEBIH_DARI_SATU_PERTANYAAN``. Pertanyaan kosong atau hanya spasi dianggap tidak ada.
    Kenetralan, dan pertanyaan material tanpa tanda tanya, tidak diperiksa (tugas reviewer).

    Args:
        isi: Field ``isi`` keluaran.
        amplop: Amplop keluaran; diterima demi signature ``ATURAN_ISI`` dan tidak dipakai.

    Returns:
        Daftar kode pelanggaran; kosong bila sesuai.
    """
    pertanyaan = isi.get("one_neutral_question")
    ada = isinstance(pertanyaan, str) and bool(pertanyaan.strip())
    pelanggaran: list[str] = []
    if (isi.get("material") is True) != ada:
        pelanggaran.append(KODE_ATURAN_P04_DILANGGAR)
    if ada and pertanyaan.count("?") > 1:
        pelanggaran.append(KODE_LEBIH_DARI_SATU_PERTANYAAN)
    return pelanggaran


class ParameterP04(BaseModel):
    """Parameter pengajuan P04.

    Hanya dua kode; teks bebas (``klaim``, ``keputusan_terkait``) tidak boleh di sini karena
    ``parameter`` berada di luar gerbang PII, jadi keduanya dikirim sebagai sumber.

    Attributes:
        narasi_id: Id kasus narasi yang menjadi sasaran.
        periode: Periode kasus apa adanya; pola ``POLA_PERIODE_AI`` (mis. ``2026/27``).
    """

    model_config = ConfigDict(extra="forbid")

    narasi_id: str = Field(pattern=_POLA_UUID, max_length=36)
    periode: str = Field(pattern=POLA_PERIODE_AI, max_length=100)
