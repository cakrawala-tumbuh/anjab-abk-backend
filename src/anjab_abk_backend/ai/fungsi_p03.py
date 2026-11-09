"""Definisi fungsi AI P03 versi terbatas: tag peran berdasarkan mandat formal saja.

P03 penuh (library prompt YPII, Role & Context Tagging) mengusulkan pemilik tugas menurut peran,
jenjang, dan formal-aktual dari kandidat tugas P02, semesta peran, dan sumber penugasan
berperiode. Sumber penugasan aktual belum ada di aplikasi, jadi versi ini sengaja terbatas:

- masukan hanya usulan P02 yang sudah diterima reviewer (``USULAN_AI``) dan baris mandat formal
  katalog TI (``ti_uraian_tugas_jabatan``, jenis ``KATALOG_TI``) untuk uraian yang dirujuk usulan
  itu, dari semua jabatan pemegangnya;
- ``assignment_sources`` tidak pernah dikirim; tiap tag berdasar ``MANDAT_FORMAL`` dengan status
  aktual tetap ``BELUM_DIKETAHUI`` (dikunci ``const`` di skema);
- ``unknowns`` amplop wajib terisi (ketiadaan sumber penugasan aktual).

Hasilnya hanya usulan untuk Tim Kajian; mandat formal bukan bukti tugas dikerjakan (KAI:13).
Versi penuh menunggu model penugasan berperiode dan roster unit.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .fungsi_p02 import AWALAN_SUMBER_URAIAN, JENIS_SUMBER_KATALOG_TI, POLA_KODE_P02
from .gateway import FungsiAi
from .keluaran import normalkan_kutipan
from .masukan import POLA_PERIODE_AI
from .redaksi import SumberAi

__all__ = [
    "DASAR_TAG_P03",
    "FIELD_SUMBER_MANDAT_P03",
    "FUNGSI_P03",
    "INSTRUKSI_P03",
    "KODE_RUJUKAN_TAK_DIKENAL",
    "KODE_TANPA_DASAR_MANDAT",
    "KODE_UNKNOWNS_KOSONG",
    "SKEMA_ISI_P03",
    "STATUS_AKTUAL_P03",
    "ParameterP03",
    "aturan_p03",
    "id_sumber_mandat",
    "sumber_mandat_p03",
    "teks_sumber_mandat_p03",
    "uraian_dirujuk_p02",
]

DASAR_TAG_P03 = "MANDAT_FORMAL"
"""Satu-satunya dasar tag yang sah pada versi terbatas."""

STATUS_AKTUAL_P03 = "BELUM_DIKETAHUI"
"""Satu-satunya status aktual yang sah: penugasan aktual tidak pernah dinyatakan."""

KODE_RUJUKAN_TAK_DIKENAL = "RUJUKAN_TAK_DIKENAL"
"""Kode pelanggaran: ada ``source_ids`` tag yang tidak tercantum di ``amplop.source_refs``."""

KODE_TANPA_DASAR_MANDAT = "TANPA_DASAR_MANDAT"
"""Kode pelanggaran: ada tag tanpa satu pun ``source_ids`` berawalan ``uraian:`` (mandat)."""

KODE_UNKNOWNS_KOSONG = "UNKNOWNS_KOSONG"
"""Kode pelanggaran: ``unknowns`` amplop kosong, padahal ketiadaan sumber penugasan aktual
wajib disebut."""

_KUNCI_RUJUKAN_P02 = ("task_candidates", "duplicate_suspicions", "split_merge_rationale")
"""Bagian ``isi`` P02 yang memuat ``source_ids``."""

FIELD_SUMBER_MANDAT_P03 = (
    "jabatan_kode",
    "jabatan_nama",
    "kode",
    "unit",
    "tugas_pokok",
    "detil_tugas",
    "uraian",
)
"""Satu-satunya kunci yang boleh muncul pada teks sumber mandat: kode/nama jabatan dan tugas,
tanpa nilai standar dan tanpa data orang."""

INSTRUKSI_P03 = """\
Fungsi: mengusulkan jabatan pemegang mandat formal untuk kandidat tugas hasil normalisasi \
(P02) yang sudah diterima reviewer. Sumber berpenanda "usulan:" memuat kandidat tugas \
(task_candidates; kandidat_ke adalah indeks berbasis nol pada daftar itu). Sumber berpenanda \
"uraian:" adalah baris mandat formal katalog: satu jabatan memegang satu uraian tugas. \
Hasilnya hanya usulan; bukan keputusan dan bukan penugasan.

Aturan fungsi:
1. Mandat formal tidak sama dengan dilakukan. Jangan menyatakan atau menyiratkan bahwa \
jabatan mana pun sedang atau sudah mengerjakan tugas itu.
2. Jangan mengasumsikan penugasan tetap. Tidak ada sumber penugasan aktual (roster, \
penugasan berperiode); karena itu dasar setiap tag selalu MANDAT_FORMAL dan status_aktual \
selalu BELUM_DIKETAHUI.
3. Tiap tag menunjuk minimal satu source_id berpenanda "uraian:" yang menjadi dasar \
mandatnya, ditambah source_id usulan bila perlu. jabatan_kode harus jabatan pada baris \
mandat itu.
4. Bila satu kandidat dipegang beberapa jabatan, atau jenjang/unit yang dimaksud tidak \
tercantum di sumber, catat pada owner_ambiguities beserta alasan dan jabatan kandidatnya; \
jangan memilih diam-diam.
5. unknowns wajib menyebut bahwa sumber penugasan aktual tidak tersedia, ditambah hal lain \
yang belum diketahui.
6. Gunakan hanya source_id yang ada pada sumber; jangan memakai pengetahuan lain. Parameter \
jabatan_kode dan periode hanya kode konteks, bukan sumber fakta. Tulis seluruh keluaran \
dalam bahasa Indonesia.\
"""

SKEMA_ISI_P03: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tag_candidates", "owner_ambiguities"],
    "properties": {
        "tag_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "kandidat_ke",
                    "jabatan_kode",
                    "dasar",
                    "status_aktual",
                    "source_ids",
                ],  # fmt: skip
                "properties": {
                    "kandidat_ke": {"type": "integer"},
                    "jabatan_kode": {"type": "string"},
                    "dasar": {"type": "string", "const": DASAR_TAG_P03},
                    "status_aktual": {"type": "string", "const": STATUS_AKTUAL_P03},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "owner_ambiguities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kandidat_ke", "alasan", "jabatan_kode_kandidat"],
                "properties": {
                    "kandidat_ke": {"type": "integer"},
                    "alasan": {"type": "string"},
                    "jabatan_kode_kandidat": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}
"""Skema field ``isi`` P03 terbatas. ``dasar`` dan ``status_aktual`` dikunci ``const``; tanpa
``minItems``/``minLength`` (minimal satu sumber mandat ditagih ``aturan_p03``)."""

FUNGSI_P03 = FungsiAi(
    kode="P03",
    prompt_version="p03-terbatas-1",
    instruksi=INSTRUKSI_P03,
    skema_isi=SKEMA_ISI_P03,
)
"""Definisi fungsi P03 versi terbatas untuk katalog."""


class ParameterP03(BaseModel):
    """Parameter pengajuan P03 terbatas.

    Hanya kode; tidak ada teks bebas karena ``parameter`` berada di luar gerbang PII.

    Attributes:
        jabatan_kode: Kode jabatan sasaran usulan P02 (``jabatan.kode``).
        periode: Kode periode konteks; pola ``POLA_PERIODE_AI`` (mis. ``2026/27``).
    """

    model_config = ConfigDict(extra="forbid")

    jabatan_kode: str = Field(pattern=POLA_KODE_P02, max_length=30)
    periode: str = Field(pattern=POLA_PERIODE_AI, max_length=100)


def uraian_dirujuk_p02(isi: dict[str, Any] | None) -> list[str]:
    """Kumpulkan id uraian yang dirujuk ``source_ids`` isi usulan P02.

    Hanya ``source_ids`` berawalan ``uraian:`` pada ``task_candidates``,
    ``duplicate_suspicions``, dan ``split_merge_rationale`` yang diambil; awalan dibuang,
    duplikat dihapus, urutan kemunculan pertama dipertahankan. Bentuk yang tak terduga
    (bukan daftar/objek/string) dilewati tanpa galat.

    Args:
        isi: Field ``isi`` usulan P02, atau ``None`` (usulan tanpa isi).

    Returns:
        Daftar id ``ti_uraian_tugas``; kosong bila tidak ada rujukan uraian.
    """
    hasil: dict[str, None] = {}
    for kunci in _KUNCI_RUJUKAN_P02:
        daftar = (isi or {}).get(kunci)
        for elemen in daftar if isinstance(daftar, list) else []:
            ids = elemen.get("source_ids") if isinstance(elemen, dict) else None
            for sid in ids if isinstance(ids, list) else []:
                if isinstance(sid, str) and sid.startswith(AWALAN_SUMBER_URAIAN):
                    uid = sid[len(AWALAN_SUMBER_URAIAN) :]
                    if uid:
                        hasil.setdefault(uid, None)
    return list(hasil)


def id_sumber_mandat(uraian_tugas_id: str, jabatan_id: str) -> str:
    """Bentuk ``source_id`` satu baris mandat (pasangan uraian-jabatan).

    Satu uraian bisa dipegang beberapa jabatan, jadi id jabatan ikut di belakang ``@`` agar
    tiap baris unik sambil mempertahankan awalan ``uraian:`` yang ditagih ``aturan_p03``.

    Args:
        uraian_tugas_id: Id ``ti_uraian_tugas``.
        jabatan_id: Id jabatan pemegang mandat.

    Returns:
        ``uraian:<uraian_tugas_id>@<jabatan_id>``.
    """
    return f"{AWALAN_SUMBER_URAIAN}{uraian_tugas_id}@{jabatan_id}"


def teks_sumber_mandat_p03(nilai: dict[str, Any]) -> str:
    """Susun teks sumber mandat dari kode/nama jabatan dan field tugas satu baris katalog.

    Hanya kunci di ``FIELD_SUMBER_MANDAT_P03`` yang dipakai, dalam urutan tetap, satu baris
    ``kunci: nilai`` per field; nilai ``None`` atau string kosong dilewati. Kunci lain pada
    ``nilai`` diabaikan sehingga tidak pernah ikut terkirim.

    Args:
        nilai: Pemetaan nama field ke nilai.

    Returns:
        Teks deterministik untuk baris itu.
    """
    baris = []
    for kunci in FIELD_SUMBER_MANDAT_P03:
        isi = nilai.get(kunci)
        if isi is None or (isinstance(isi, str) and not isi.strip()):
            continue
        baris.append(f"{kunci}: {' '.join(str(isi).split())}")
    return "\n".join(baris)


def sumber_mandat_p03(uraian_tugas_id: str, jabatan_id: str, nilai: dict[str, Any]) -> SumberAi:
    """Bungkus satu baris mandat formal sebagai ``SumberAi`` berjenis ``KATALOG_TI``.

    Args:
        uraian_tugas_id: Id ``ti_uraian_tugas``.
        jabatan_id: Id jabatan pemegang (hanya masuk ``source_id``, tidak masuk teks).
        nilai: Field baris mandat (lihat ``teks_sumber_mandat_p03``).

    Returns:
        Sumber dengan ``source_id`` dari ``id_sumber_mandat`` dan ``source_hash`` SHA-256
        teksnya.
    """
    teks = teks_sumber_mandat_p03(nilai)
    return SumberAi(
        source_id=id_sumber_mandat(uraian_tugas_id, jabatan_id),
        source_hash=hashlib.sha256(teks.encode("utf-8")).hexdigest(),
        jenis=JENIS_SUMBER_KATALOG_TI,
        teks=teks,
    )


def aturan_p03(isi: dict[str, Any], amplop: dict[str, Any]) -> list[str]:
    """Periksa keluaran P03 yang sudah lolos skema (terdaftar di ``ATURAN_ISI``).

    - Setiap ``source_ids`` pada ``tag_candidates`` harus tercantum di ``amplop["source_refs"]``;
      bila tidak, ``RUJUKAN_TAK_DIKENAL``.
    - Setiap tag minimal satu ``source_ids`` berawalan ``uraian:``; bila tidak,
      ``TANPA_DASAR_MANDAT``.
    - ``amplop["unknowns"]`` harus memuat minimal satu butir tak kosong; bila tidak,
      ``UNKNOWNS_KOSONG``.

    Tiap kode paling banyak sekali, tanpa indeks maupun teks keluaran. Daftar tak kosong membuat
    usulan ``MANUAL``.

    Args:
        isi: Field ``isi`` keluaran.
        amplop: Amplop keluaran (hasil ``_amplop``), memuat ``source_refs`` dan ``unknowns``.

    Returns:
        Daftar kode pelanggaran; kosong bila sesuai.
    """
    dikenal = {ref.get("source_id") for ref in amplop.get("source_refs") or []}
    pelanggaran: list[str] = []
    for tag in isi.get("tag_candidates") or []:
        ids = list(tag.get("source_ids") or [])
        if any(sid not in dikenal for sid in ids) and KODE_RUJUKAN_TAK_DIKENAL not in pelanggaran:
            pelanggaran.append(KODE_RUJUKAN_TAK_DIKENAL)
        mandat = any(isinstance(s, str) and s.startswith(AWALAN_SUMBER_URAIAN) for s in ids)
        if not mandat and KODE_TANPA_DASAR_MANDAT not in pelanggaran:
            pelanggaran.append(KODE_TANPA_DASAR_MANDAT)
    unknowns = amplop.get("unknowns") or []
    if not any(isinstance(u, str) and normalkan_kutipan(u) for u in unknowns):
        pelanggaran.append(KODE_UNKNOWNS_KOSONG)
    return pelanggaran
