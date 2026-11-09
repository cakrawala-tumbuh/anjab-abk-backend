"""Definisi fungsi AI P07: kartu keputusan satu halaman untuk Tim, tanpa status otorisasi.

P07 (library prompt YPII, Executive Decision Pack Writer, PRM:48-52) menyusun kartu keputusan:
masalah, bukti, alternatif, batas angka, risiko, dan persyaratan, ditambah daftar tanda tangan
yang masih dibutuhkan (PRIORITY dan CHANGE terpisah, I07:68). Kartu mendahului tanda tangan dan
tidak boleh dibaca sebagai izin perubahan (KTK:139), jadi:

- skema ``isi`` tidak punya kunci ``authorization_state`` (``additionalProperties: false``),
  dan status tiap tanda tangan dikunci ``BELUM_DITANDATANGANI``;
- status otorisasi yang sebenarnya diisi server (``ai/otorisasi_redesain.py``) dan disimpan di
  ``ai_usulan.konteks_server``, bukan di keluaran model.

Pengajuan hanya sah untuk masalah yang lolos gerbang F4 dan punya minimal satu alternatif
(``periksa_syarat_p07``). Kartu hanya untuk Tim; rute Yayasan tidak membaca ``ai_usulan``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from ..schemas.pengajuan_ai import POLA_UUID
from .fungsi_p06 import KODE_STATUS_TERLARANG, memuat_status_terlarang
from .gateway import FungsiAi
from .masukan import POLA_PERIODE_AI
from .syarat_f4 import VERSI_SYARAT_F4

__all__ = [
    "FUNGSI_P07",
    "INSTRUKSI_P07",
    "JENIS_SIGNOFF_P07",
    "KODE_CHANGE_TIDAK_DISEBUT",
    "KODE_RUJUKAN_TAK_DIKENAL",
    "KODE_STATUS_TERLARANG",
    "KODE_UNKNOWNS_KOSONG",
    "SKEMA_ISI_P07",
    "STATUS_SIGNOFF_P07",
    "ParameterP07",
    "aturan_p07",
]

JENIS_SIGNOFF_P07 = ("PRIORITY", "CHANGE")
"""Dua jenis tanda tangan Yayasan yang terpisah (I07:68)."""

STATUS_SIGNOFF_P07 = "BELUM_DITANDATANGANI"
"""Satu-satunya status tanda tangan yang boleh ditulis model."""

KODE_RUJUKAN_TAK_DIKENAL = "RUJUKAN_TAK_DIKENAL"
"""Kode pelanggaran: ada ``decision_card.bukti[].source_ids`` atau
``decision_card.alternatif[].source_ids`` yang tidak tercantum di ``amplop.source_refs``, atau
daftarnya kosong (minimal satu ditagih di sini, bukan lewat ``minItems``)."""

KODE_CHANGE_TIDAK_DISEBUT = "CHANGE_TIDAK_DISEBUT"
"""Kode pelanggaran: tidak ada ``required_signoffs`` ber-``jenis`` ``CHANGE``. Kartu wajib
menyebut bahwa perubahan masih butuh tanda tangan terpisah."""

KODE_UNKNOWNS_KOSONG = "UNKNOWNS_KOSONG"
"""Kode pelanggaran: ``amplop.unknowns`` kosong. Penerima lengkap belum dimodelkan aplikasi,
jadi kartu selalu punya hal yang belum diketahui."""

INSTRUKSI_P07 = """\
Fungsi: menyusun kartu keputusan satu halaman untuk Tim Kajian atas satu masalah redesain \
sekolah. Sumber berpenanda "masalah:", "proses:", "langkah:", "bukti:", "koreksi:", dan \
"konfirmasi:" memuat data masalah yang klaimnya sudah diperkuat Tim; "alternatif:" memuat \
alternatif yang sudah dicatat Tim; "otorisasi:" memuat cuplikan status telaah, pemutus, \
keputusan, dan prioritas final yang dibaca server; "usulan:" (bila ada) memuat draf opsi P06 \
yang sudah diterima reviewer. Orang hanya disebut lewat kode samaran. Kartu ini hanya bahan \
untuk Tim; bukan keputusan dan bukan izin perubahan.

Aturan fungsi:
1. Isi decision_card: masalah (ringkas), bukti (tiap butir menunjuk minimal satu source_id), \
alternatif (tiap butir menunjuk minimal satu source_id, termasuk "alternatif:" yang dirujuk), \
batas_angka (apa yang belum diketahui atau belum terverifikasi tentang angka; jangan menghitung \
FTE, jam kerja, atau formasi), risiko, dan persyaratan.
2. Jangan menulis status otorisasi. Status telaah, keputusan, dan prioritas final pada sumber \
"otorisasi:" hanya untuk dibaca; jangan menyatakan perubahan disetujui, ditandatangani, atau \
boleh dijalankan, dan jangan memberi status VERIFIED, READY, atau APPROVE.
3. required_signoffs wajib menyebut tanda tangan PRIORITY dan CHANGE secara terpisah, \
masing-masing dengan pihak yang menandatangani (mis. Yayasan) dan status BELUM_DITANDATANGANI.
4. limitation wajib berisi minimal satu batasan kartu. Penerima tugas selain yang tercatat pada \
sumber alternatif belum diketahui; tulis pada unknowns, jangan ditebak.
5. Gunakan hanya source_id yang ada pada sumber; jangan memakai pengetahuan lain. Parameter \
masalah_id, periode, versi_syarat_f4, dan usulan_p06_id hanya kode konteks, bukan sumber \
fakta. Tulis seluruh keluaran dalam bahasa Indonesia.\
"""


def _butir_bersumber(nama_teks: str) -> dict:
    """Skema daftar butir ``{<nama_teks>: string, source_ids: [string]}``."""
    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": [nama_teks, "source_ids"],
            "properties": {
                nama_teks: {"type": "string"},
                "source_ids": {"type": "array", "items": {"type": "string"}},
            },
        },
    }


SKEMA_ISI_P07: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decision_card", "limitation", "required_signoffs"],
    "properties": {
        "decision_card": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "masalah",
                "bukti",
                "alternatif",
                "batas_angka",
                "risiko",
                "persyaratan",
            ],
            "properties": {
                "masalah": {"type": "string"},
                "bukti": _butir_bersumber("pernyataan"),
                "alternatif": _butir_bersumber("ringkasan"),
                "batas_angka": {"type": "string"},
                "risiko": {"type": "array", "items": {"type": "string"}},
                "persyaratan": {"type": "array", "items": {"type": "string"}},
            },
        },
        "limitation": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "required_signoffs": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["jenis", "pihak", "status"],
                "properties": {
                    "jenis": {"type": "string", "enum": list(JENIS_SIGNOFF_P07)},
                    "pihak": {"type": "string"},
                    "status": {"type": "string", "const": STATUS_SIGNOFF_P07},
                },
            },
        },
    },
}
"""Skema field ``isi`` P07. Tanpa kunci ``authorization_state`` di level mana pun
(``additionalProperties: false``) dan tanpa field numerik. ``limitation`` memakai
``minItems: 1`` (nilai yang didukung structured output; pengecualian konvensi seperti P06/P08)
karena Keputusan Desain #125 menuntut minimal satu batasan; minimal satu ``source_ids`` per butir
ditagih ``aturan_p07``, ``CHANGE`` pada ``required_signoffs`` juga."""

FUNGSI_P07 = FungsiAi(
    kode="P07",
    prompt_version="p07-1",
    instruksi=INSTRUKSI_P07,
    skema_isi=SKEMA_ISI_P07,
)
"""Definisi fungsi P07 untuk katalog."""


class ParameterP07(BaseModel):
    """Parameter pengajuan P07.

    Hanya kode; tidak ada teks bebas karena ``parameter`` berada di luar gerbang PII. Status
    otorisasi sengaja tidak ada di sini: ia disimpan di ``ai_usulan.konteks_server`` dan
    dikirim ke model hanya sebagai sumber ``otorisasi:<masalah_id>``.

    Attributes:
        masalah_id: Id ``redesain_masalah`` sasaran (UUID).
        periode: Kode periode konteks; pola ``POLA_PERIODE_AI`` (mis. ``2026/27``).
        versi_syarat_f4: Versi definisi gerbang F4 yang dipakai saat pengajuan; selalu
            ``VERSI_SYARAT_F4``.
        usulan_p06_id: Id usulan P06 yang ikut dirangkai sebagai sumber, atau ``None``.
    """

    model_config = ConfigDict(extra="forbid")

    masalah_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$", max_length=36)
    periode: str = Field(pattern=POLA_PERIODE_AI, max_length=100)
    versi_syarat_f4: Literal["sementara-2026-11"] = VERSI_SYARAT_F4
    usulan_p06_id: str | None = Field(default=None, pattern=POLA_UUID, max_length=36)


def _butir(isi: dict[str, Any], kunci: str) -> list[dict[str, Any]]:
    """Ambil butir dict pada ``isi["decision_card"][kunci]`` (daftar kosong bila tak ada)."""
    kartu = isi.get("decision_card")
    nilai = kartu.get(kunci) if isinstance(kartu, dict) else None
    return [b for b in nilai if isinstance(b, dict)] if isinstance(nilai, list) else []


def aturan_p07(isi: dict[str, Any], amplop: dict[str, Any]) -> list[str]:
    """Periksa keluaran P07 yang sudah lolos skema (terdaftar di ``ATURAN_ISI``).

    - Setiap ``decision_card.bukti[].source_ids`` dan ``decision_card.alternatif[].source_ids``
      harus tercantum di ``amplop["source_refs"]`` dan tiap daftar minimal satu; bila tidak,
      ``RUJUKAN_TAK_DIKENAL``.
    - Bila ada nilai string isi yang memuat kata utuh ``VERIFIED``, ``READY``, atau ``APPROVE``
      (aturan P06, ``memuat_status_terlarang``), ``STATUS_TERLARANG``.
    - Bila tidak ada ``required_signoffs`` ber-``jenis`` ``CHANGE``, ``CHANGE_TIDAK_DISEBUT``.
    - Bila ``amplop["unknowns"]`` kosong atau tidak ada, ``UNKNOWNS_KOSONG``.

    Tiap kode paling banyak sekali, urut seperti di atas, tanpa indeks maupun teks keluaran.
    Daftar tak kosong membuat usulan ``MANUAL``.

    Args:
        isi: Field ``isi`` keluaran.
        amplop: Amplop keluaran (hasil ``_amplop``), memuat ``source_refs`` dan ``unknowns``.

    Returns:
        Daftar kode pelanggaran; kosong bila sesuai.

    Example:
        >>> aturan_p07({"required_signoffs": []}, {"unknowns": ["penerima"]})
        ['CHANGE_TIDAK_DISEBUT']
    """
    dikenal = {ref.get("source_id") for ref in amplop.get("source_refs") or []}
    pelanggaran: list[str] = []
    for butir in [*_butir(isi, "bukti"), *_butir(isi, "alternatif")]:
        ids = list(butir.get("source_ids") or [])
        if not ids or any(sid not in dikenal for sid in ids):
            pelanggaran.append(KODE_RUJUKAN_TAK_DIKENAL)
            break
    if memuat_status_terlarang(isi):
        pelanggaran.append(KODE_STATUS_TERLARANG)
    signoff = isi.get("required_signoffs")
    signoff = [s for s in signoff if isinstance(s, dict)] if isinstance(signoff, list) else []
    if not any(s.get("jenis") == "CHANGE" for s in signoff):
        pelanggaran.append(KODE_CHANGE_TIDAK_DISEBUT)
    if not amplop.get("unknowns"):
        pelanggaran.append(KODE_UNKNOWNS_KOSONG)
    return pelanggaran
