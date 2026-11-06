"""Definisi fungsi AI P01: ekstraksi fakta dan metadata dari satu dokumen sumber.

P01 mengambil fakta berkutipan dari satu baris ``narasi_sumber`` yang izin AI-nya tercatat.
Hasilnya hanya usulan untuk Tim Kajian. Dokumen normatif (SOP, kebijakan, pedoman) menunjukkan
yang seharusnya, bukan yang terlaksana, jadi fungsi ini dilarang menyimpulkan praktik aktual
darinya. Fungsi ini tidak mengubah sumber dan tidak membuat narasi.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .gateway import FungsiAi
from .keluaran import normalkan_kutipan

__all__ = [
    "FUNGSI_P01",
    "INSTRUKSI_P01",
    "KODE_SPAN_FAKTA_TIDAK_DITEMUKAN",
    "PENILAIAN_SUMBER_P01",
    "POLA_KODE_P01",
    "SIFAT_FAKTA_P01",
    "SKEMA_ISI_P01",
    "ParameterP01",
    "aturan_p01",
]

SIFAT_FAKTA_P01 = ("NORMATIF", "DESKRIPTIF_DOKUMEN")
"""Sifat fakta: ``NORMATIF`` (yang seharusnya) atau ``DESKRIPTIF_DOKUMEN`` (dokumen sendiri
mencatat kejadian atau keadaan)."""

PENILAIAN_SUMBER_P01 = ("CUKUP", "TERBATAS", "TIDAK_JELAS")
"""Penilaian mutu sumber yang sah."""

POLA_KODE_P01 = r"^[A-Za-z0-9_.:-]+$"
"""Pola nilai parameter: kode tanpa spasi, tanpa teks bebas."""

INSTRUKSI_P01 = """\
Fungsi: mengekstrak fakta dan metadata dari satu dokumen sumber untuk Tim Kajian. Hasilnya \
hanya saran berkutipan; bukan narasi dan bukan keputusan.

Aturan fungsi:
1. Ambil hanya yang tertulis di sumber; jangan memakai pengetahuan lain dan jangan menyimpulkan \
hal yang tidak tertulis.
2. Dokumen normatif (SOP, kebijakan, peraturan, pedoman) menunjukkan yang seharusnya, bukan yang \
terlaksana. Jangan menyatakan atau menyiratkan bahwa suatu praktik sudah atau sedang terlaksana \
berdasarkan dokumen normatif; tandai faktanya NORMATIF. Tandai DESKRIPTIF_DOKUMEN hanya bila \
dokumen itu sendiri mencatat kejadian atau keadaan (mis. laporan atau notulen), dan tulis \
faktanya sebagai catatan dokumen, bukan sebagai kebenaran di lapangan.
3. Anda tidak mengarang angka: setiap angka pada keluaran harus tertulis pada sumber.
4. Tiap fakta punya kutipan: source_id sumbernya dan span yang persis dari teks sumber itu, \
dan kutipan itu juga dicantumkan pada cited_spans.
5. Anda tidak mengisi persetujuan, skor, atau keputusan, dan tidak menilai apakah praktik \
benar, layak, atau memadai.
6. source_quality hanya menilai keterbacaan dan kelengkapan sumber (CUKUP, TERBATAS, \
TIDAK_JELAS) beserta alasannya.
7. Bila sumber tidak memuat fakta yang dapat diekstrak, kembalikan status EVIDENCE_GAP, isi \
factual_extracts dengan daftar kosong, dan isi unknowns dengan apa yang tidak ditemukan.
8. Ketidakpastian masuk uncertainties; hal yang tidak dapat Anda periksa masuk limitations. \
Parameter peran_ref dan periode hanya kode konteks, bukan sumber fakta. Tulis seluruh keluaran \
dalam bahasa Indonesia.\
"""

SKEMA_ISI_P01: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["factual_extracts", "source_quality", "uncertainties", "limitations"],
    "properties": {
        "factual_extracts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["fakta", "sifat", "source_id", "span"],
                "properties": {
                    "fakta": {"type": "string"},
                    "sifat": {"type": "string", "enum": list(SIFAT_FAKTA_P01)},
                    "source_id": {"type": "string"},
                    "span": {"type": "string"},
                },
            },
        },
        "source_quality": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["source_id", "penilaian", "alasan"],
                "properties": {
                    "source_id": {"type": "string"},
                    "penilaian": {"type": "string", "enum": list(PENILAIAN_SUMBER_P01)},
                    "alasan": {"type": "string"},
                },
            },
        },
        "uncertainties": {"type": "array", "items": {"type": "string"}},
        "limitations": {"type": "array", "items": {"type": "string"}},
    },
}
"""Skema field ``isi`` P01: tanpa ``if/then``, ``minLength``, ``minItems``, dan tanpa field
persetujuan, skor, atau keputusan. ``qa_flags`` milik server (``kode_qa``), bukan skema."""

FUNGSI_P01 = FungsiAi(
    kode="P01",
    prompt_version="p01-1",
    instruksi=INSTRUKSI_P01,
    skema_isi=SKEMA_ISI_P01,
)
"""Definisi fungsi P01 untuk katalog."""


class ParameterP01(BaseModel):
    """Parameter pengajuan P01.

    Hanya dua kode; tidak ada teks bebas karena ``parameter`` berada di luar gerbang PII
    (konteks peran PRM:14 dinyatakan sebagai kode).

    Attributes:
        peran_ref: Kode peran yang menjadi konteks ekstraksi.
        periode: Kode periode konteks ekstraksi.
    """

    model_config = ConfigDict(extra="forbid")

    peran_ref: str = Field(pattern=POLA_KODE_P01, max_length=100)
    periode: str = Field(pattern=POLA_KODE_P01, max_length=100)


KODE_SPAN_FAKTA_TIDAK_DITEMUKAN = "SPAN_FAKTA_TIDAK_DITEMUKAN"
"""Kode pelanggaran: ada ``factual_extracts[].span`` kosong, ber-``source_id`` asing, atau tak
terbukti lewat ``cited_spans``."""


def aturan_p01(isi: dict[str, Any], amplop: dict[str, Any]) -> list[str]:
    """Periksa keluaran P01 yang sudah lolos skema (terdaftar di ``ATURAN_ISI``).

    Satu fakta terbukti bila ``span``-nya (setelah ``normalkan_kutipan``) tidak kosong dan
    merupakan substring dari kutipan ternormalkan pada setidaknya satu elemen
    ``amplop["cited_spans"]`` ber-``source_id`` sama; perbandingan peka huruf besar-kecil.
    ``cited_spans`` sudah diverifikasi terhadap sumber oleh ``cek_keluaran`` sebelum run
    ``LOLOS``, jadi teks sumber tidak perlu dibaca ulang (``ai_run.masukan`` dikosongkan saat
    ``tutup``). Kode dikembalikan paling banyak sekali, tanpa indeks maupun teks keluaran.

    Args:
        isi: Field ``isi`` keluaran.
        amplop: Amplop keluaran (hasil ``_amplop``), memuat ``cited_spans``.

    Returns:
        ``[KODE_SPAN_FAKTA_TIDAK_DITEMUKAN]`` bila ada fakta tak terbukti; kosong bila sesuai.
    """
    kutipan: dict[str, list[str]] = {}
    for kutip in amplop.get("cited_spans") or []:
        kutipan.setdefault(kutip["source_id"], []).append(normalkan_kutipan(kutip["span"]))
    for fakta in isi.get("factual_extracts") or []:
        span = normalkan_kutipan(fakta["span"])
        if not span or not any(span in k for k in kutipan.get(fakta["source_id"], [])):
            return [KODE_SPAN_FAKTA_TIDAK_DITEMUKAN]
    return []
