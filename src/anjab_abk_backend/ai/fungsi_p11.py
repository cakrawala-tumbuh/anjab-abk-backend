"""Definisi fungsi AI P11: pengusul kandidat konteks redesain dari katalog konteks dan masalah.

P11 (Pengusul Konteks) membaca katalog ``redesain_konteks`` yang aktif dan, opsional, daftar
``redesain_masalah`` hasil olah data ANJAB sebelumnya, lalu mengusulkan 1-5 kandidat isian
Konteks (tema, ruang dugaan, sumber draf, batas pemeriksaan, saran gelombang). Sumbernya dirakit
``rakit_sumber_konteks`` (``ai/sumber_konteks.py``, jenis ``REDESAIN``); dokumen resmi pendukung
ikut dengan jenisnya sendiri.

Katalog konteks tidak punya objek tunggal, jadi usulan bersasaran ``REDESAIN_KONTEKS`` dengan
``sasaran_id`` tetap ``SASARAN_KATALOG_KONTEKS``. Hasilnya hanya usulan di ``ai_usulan`` yang
diputus Tim Kajian; menulis ke ``redesain_konteks`` adalah jalur terpisah. Fungsi ini nonaktif
bawaan (``AI_FUNGSI_AKTIF``).
"""

from __future__ import annotations

from typing import Annotated, Any, get_args

from pydantic import BaseModel, ConfigDict, Field

from ..redesain.schemas.kosakata import Gelombang
from .gateway import FungsiAi

__all__ = [
    "FUNGSI_P11",
    "INSTRUKSI_P11",
    "KODE_KANDIDAT_BERLEBIH",
    "KODE_KONTEKS_TAK_DIKENAL",
    "KODE_RUJUKAN_TAK_DIKENAL",
    "KODE_TEMA_TERLALU_PANJANG",
    "MAKS_KANDIDAT_P11",
    "MAKS_TEMA_P11",
    "SASARAN_KATALOG_KONTEKS",
    "SKEMA_ISI_P11",
    "ParameterP11",
    "aturan_p11",
]

SASARAN_KATALOG_KONTEKS = "KATALOG"
"""``sasaran_id`` usulan P11: katalog konteks redesain tidak punya objek tunggal."""

MAKS_KANDIDAT_P11 = 5
"""Jumlah kandidat konteks maksimum yang boleh diminta per pengajuan."""

MAKS_TEMA_P11 = 200
"""Panjang ``tema`` maksimum (sama dengan kolom ``redesain_konteks.tema``)."""

KODE_RUJUKAN_TAK_DIKENAL = "RUJUKAN_TAK_DIKENAL"
"""Kode pelanggaran: ada ``konteks_candidates[].source_ids`` yang tidak tercantum di
``amplop.source_refs``, atau daftarnya kosong (minimal satu ditagih di sini karena konvensi
skema repo tidak memakai ``minItems`` untuk field ini)."""

KODE_KONTEKS_TAK_DIKENAL = "KODE_KONTEKS_TAK_DIKENAL"
"""Kode pelanggaran: ada ``mirip_kode`` terisi yang bukan kode konteks aktif saat pengajuan
(``kode_konteks_ada``)."""

KODE_KANDIDAT_BERLEBIH = "KANDIDAT_BERLEBIH"
"""Kode pelanggaran: jumlah ``konteks_candidates`` melebihi ``jumlah_kandidat`` yang diminta."""

KODE_TEMA_TERLALU_PANJANG = "TEMA_TERLALU_PANJANG"
"""Kode pelanggaran: ada ``tema`` lebih dari ``MAKS_TEMA_P11`` karakter (skema structured output
tidak boleh memakai ``maxLength``)."""

INSTRUKSI_P11 = """\
Fungsi: mengusulkan kandidat isian Konteks redesain untuk yayasan pendidikan, dari katalog \
konteks yang sudah ada dan daftar masalah hasil olah data analisis jabatan sebelumnya. Sumber \
berpenanda "konteks:" memuat satu konteks aktif (kode, tema, gelombang, ruang_dugaan, \
sumber_draft, batas_pemeriksaan); "masalah:" memuat satu hipotesis masalah beserta kode \
konteksnya; sumber lain adalah dokumen resmi pendukung. Hasilnya hanya usulan untuk Tim Kajian; \
bukan keputusan.

Aturan fungsi:
1. Konteks adalah ruang dugaan, BUKAN temuan. Jangan menyatakan atau menyiratkan bahwa masalah \
sudah terbukti.
2. Usulkan paling banyak sebanyak parameter jumlah_kandidat. Tiap kandidat mengisi tema (paling \
panjang 200 karakter), ruang_dugaan, sumber_draft, batas_pemeriksaan, dan gelombang_saran.
3. batas_pemeriksaan menyebut apa yang belum diperiksa atau belum dapat disimpulkan.
4. sumber_draft merujuk sumber yang dipakai; tiap kandidat menunjuk minimal satu source_id \
pendukung pada source_ids.
5. Jangan menyebut nama orang, nama sekolah, atau kode orang.
6. Bila kandidat mirip konteks yang sudah ada, isi mirip_kode dengan kode konteks itu (hanya \
kode yang tercantum pada parameter kode_konteks_ada); bila tidak mirip, mirip_kode null.
7. Pertanyaan yang perlu dijawab Tim sebelum menerima kandidat ditulis pada \
reviewer_questions.
8. Gunakan hanya source_id yang ada pada sumber; jangan memakai pengetahuan lain. Parameter \
hanya kode, bukan sumber fakta. Tulis seluruh keluaran dalam bahasa Indonesia.\
"""

SKEMA_ISI_P11: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["konteks_candidates", "reviewer_questions"],
    "properties": {
        "konteks_candidates": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "tema",
                    "ruang_dugaan",
                    "sumber_draft",
                    "batas_pemeriksaan",
                    "gelombang_saran",
                    "mirip_kode",
                    "source_ids",
                ],
                "properties": {
                    "tema": {"type": "string"},
                    "ruang_dugaan": {"type": "string"},
                    "sumber_draft": {"type": "string"},
                    "batas_pemeriksaan": {"type": "string"},
                    "gelombang_saran": {"type": "string", "enum": list(get_args(Gelombang))},
                    "mirip_kode": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "reviewer_questions": {"type": "array", "items": {"type": "string"}},
    },
}
"""Skema field ``isi`` P11. ``konteks_candidates`` memakai ``minItems: 1`` (nilai yang didukung
structured output) karena Keputusan Desain #127 menuntut 1-5 kandidat; batas atas kandidat
(``KANDIDAT_BERLEBIH``), panjang ``tema`` (``TEMA_TERLALU_PANJANG``), dan minimal satu
``source_ids`` (``RUJUKAN_TAK_DIKENAL``) ditagih ``aturan_p11`` karena ``maxItems``/``maxLength``
tidak didukung. ``gelombang_saran`` dikunci ke nilai ``Gelombang``."""

FUNGSI_P11 = FungsiAi(
    kode="P11",
    prompt_version="p11-1",
    instruksi=INSTRUKSI_P11,
    skema_isi=SKEMA_ISI_P11,
)
"""Definisi fungsi P11 untuk katalog."""


class ParameterP11(BaseModel):
    """Parameter pengajuan P11.

    Hanya angka, boolean, dan kode; tidak ada teks bebas karena ``parameter`` berada di luar
    gerbang PII.

    Attributes:
        jumlah_kandidat: Jumlah kandidat maksimum yang diminta (1-5).
        sertakan_masalah: Apakah daftar masalah ikut dikirim sebagai sumber.
        kode_konteks_ada: Kode konteks aktif saat pengajuan; satu-satunya nilai sah
            ``mirip_kode``.
    """

    model_config = ConfigDict(extra="forbid")

    jumlah_kandidat: int = Field(ge=1, le=MAKS_KANDIDAT_P11)
    sertakan_masalah: bool
    kode_konteks_ada: list[Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=10)]] = (
        Field(default_factory=list)
    )


def aturan_p11(isi: dict[str, Any], amplop: dict[str, Any]) -> list[str]:
    """Periksa keluaran P11 yang sudah lolos skema (terdaftar di ``ATURAN_ISI``).

    Batas pengajuan dibaca dari ``amplop["konteks_server"]`` (``jumlah_kandidat`` dan
    ``kode_konteks_ada``) yang disisipkan penyerap dari ``ai_usulan.konteks_server``; nilai itu
    diisi server saat pengajuan, bukan oleh model. Bila tidak ada, ``jumlah_kandidat`` dianggap
    ``MAKS_KANDIDAT_P11`` dan ``kode_konteks_ada`` kosong.

    - Setiap ``konteks_candidates[].source_ids`` harus tercantum di ``amplop["source_refs"]`` dan
      tiap daftar minimal satu; bila tidak, ``RUJUKAN_TAK_DIKENAL``.
    - ``mirip_kode`` yang terisi harus ada di ``kode_konteks_ada``; bila tidak,
      ``KODE_KONTEKS_TAK_DIKENAL``.
    - Jumlah kandidat melebihi ``jumlah_kandidat``: ``KANDIDAT_BERLEBIH``.
    - ``tema`` lebih dari ``MAKS_TEMA_P11`` karakter: ``TEMA_TERLALU_PANJANG``.

    Tiap kode paling banyak sekali, urut seperti di atas, tanpa indeks maupun teks keluaran.
    Daftar tak kosong membuat usulan ``MANUAL``.

    Args:
        isi: Field ``isi`` keluaran.
        amplop: Amplop keluaran (hasil ``_amplop``) memuat ``source_refs``, ditambah kunci
            ``konteks_server`` dari penyerap.

    Returns:
        Daftar kode pelanggaran; kosong bila sesuai.

    Example:
        >>> isi = {"konteks_candidates": [{"source_ids": ["konteks:k1"], "mirip_kode": "K-99",
        ...        "tema": "Rekap nilai"}]}
        >>> batas = {"jumlah_kandidat": 3, "kode_konteks_ada": ["K-01"]}
        >>> aturan_p11(isi, {"source_refs": [{"source_id": "konteks:k1"}], "konteks_server": batas})
        ['KODE_KONTEKS_TAK_DIKENAL']
    """
    konteks = amplop.get("konteks_server") or {}
    batas = konteks.get("jumlah_kandidat") or MAKS_KANDIDAT_P11
    kode_ada = set(konteks.get("kode_konteks_ada") or [])
    dikenal = {ref.get("source_id") for ref in amplop.get("source_refs") or []}
    kandidat = [k for k in isi.get("konteks_candidates") or [] if isinstance(k, dict)]
    pelanggaran: list[str] = []
    for k in kandidat:
        ids = list(k.get("source_ids") or [])
        if not ids or any(sid not in dikenal for sid in ids):
            pelanggaran.append(KODE_RUJUKAN_TAK_DIKENAL)
            break
    if any(k.get("mirip_kode") is not None and k["mirip_kode"] not in kode_ada for k in kandidat):
        pelanggaran.append(KODE_KONTEKS_TAK_DIKENAL)
    if len(kandidat) > batas:
        pelanggaran.append(KODE_KANDIDAT_BERLEBIH)
    if any(len(str(k.get("tema") or "")) > MAKS_TEMA_P11 for k in kandidat):
        pelanggaran.append(KODE_TEMA_TERLALU_PANJANG)
    return pelanggaran
