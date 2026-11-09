"""Perakit sumber katalog konteks redesain untuk fungsi AI P11 (Pengusul Konteks).

Setiap ``redesain_konteks`` aktif menjadi satu ``SumberAi`` berjenis ``REDESAIN`` dengan
``source_id`` ``konteks:<id>``; bila diminta, setiap ``redesain_masalah`` yang konteksnya aktif
menjadi ``masalah:<id>`` berjenis sama. Labelnya sama persis dengan ``JENIS_SUMBER_REDESAIN``
yang dipakai P05-P07, jadi keputusan aktivasi ``AI_JENIS_SUMBER_DIIZINKAN`` berlaku bersama.

Batas isi teks masalah lebih sempit daripada perakit P05 (``sumber_redesain.py``): tanpa
``sekolah_id``, ``keterangan_sekolah``, ``pic_kode_orang``, maupun tautan uraian tugas. P11
hanya membutuhkan rumusan dugaan per konteks, bukan data per sekolah atau per orang. Modul ini
hanya membaca.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import RedesainKonteksModel, RedesainMasalahModel
from .redaksi import SumberAi
from .sumber_redesain import JENIS_SUMBER_REDESAIN

__all__ = [
    "FIELD_SUMBER_KONTEKS",
    "SumberKonteks",
    "rakit_sumber_konteks",
    "sumber_konteks",
    "teks_sumber_konteks",
]

FIELD_SUMBER_KONTEKS: dict[str, tuple[str, ...]] = {
    "konteks": (
        "kode",
        "tema",
        "gelombang",
        "ruang_dugaan",
        "sumber_draft",
        "batas_pemeriksaan",
    ),
    "masalah": (
        "kode",
        "konteks_kode",
        "rumusan_hipotesis",
        "sumber_awal_keterbatasan",
        "status_awal",
        "periode_acuan",
        "penjelasan_alternatif",
    ),
}
"""Satu-satunya kunci yang boleh muncul pada teks sumber per tabel. ``sekolah_id``,
``keterangan_sekolah``, dan ``pic_kode_orang`` sengaja tidak ada."""


def teks_sumber_konteks(tabel: str, nilai: dict[str, Any]) -> str:
    """Susun teks sumber satu baris dari kunci yang diizinkan untuk tabelnya.

    Hanya kunci di ``FIELD_SUMBER_KONTEKS[tabel]`` yang dipakai, dalam urutan tetap, satu baris
    ``kunci: nilai`` per field; spasi beruntun dirapatkan, nilai ``None`` atau string kosong
    dilewati. Kunci lain pada ``nilai`` diabaikan sehingga tidak pernah ikut terkirim.

    Args:
        tabel: ``konteks`` atau ``masalah``.
        nilai: Pemetaan nama field ke nilai.

    Returns:
        Teks deterministik untuk baris itu.

    Raises:
        KeyError: ``tabel`` tidak dikenal.

    Example:
        >>> teks_sumber_konteks("masalah", {"kode": "M-1", "pic_kode_orang": "P-01"})
        'kode: M-1'
    """
    baris = []
    for kunci in FIELD_SUMBER_KONTEKS[tabel]:
        isi = nilai.get(kunci)
        if isi is None or (isinstance(isi, str) and not isi.strip()):
            continue
        baris.append(f"{kunci}: {' '.join(str(isi).split())}")
    return "\n".join(baris)


def sumber_konteks(tabel: str, baris_id: str, nilai: dict[str, Any]) -> SumberAi:
    """Bungkus satu baris konteks/masalah sebagai ``SumberAi`` berjenis ``REDESAIN``.

    Args:
        tabel: ``konteks`` atau ``masalah``; menjadi awalan ``source_id``.
        baris_id: Id baris di tabelnya.
        nilai: Field baris (lihat ``teks_sumber_konteks``).

    Returns:
        Sumber dengan ``source_id`` ``<tabel>:<baris_id>`` dan ``source_hash`` SHA-256 teksnya.
    """
    teks = teks_sumber_konteks(tabel, nilai)
    return SumberAi(
        source_id=f"{tabel}:{baris_id}",
        source_hash=hashlib.sha256(teks.encode("utf-8")).hexdigest(),
        jenis=JENIS_SUMBER_REDESAIN,
        teks=teks,
    )


@dataclass(frozen=True)
class SumberKonteks:
    """Hasil ``rakit_sumber_konteks``.

    Attributes:
        sumber: Sumber ``konteks:`` (urut kode) lalu, bila diminta, ``masalah:`` (urut kode).
        kode_konteks: Kode konteks aktif, urut kode; nilai sah ``mirip_kode`` keluaran P11.
    """

    sumber: list[SumberAi]
    kode_konteks: list[str]


def rakit_sumber_konteks(session: Session, *, sertakan_masalah: bool) -> SumberKonteks:
    """Rangkai katalog konteks aktif (dan masalahnya) menjadi sumber AI ``REDESAIN``.

    Konteks hanya yang ``aktif``. Masalah hanya yang konteksnya aktif, sehingga setiap
    ``konteks_kode`` pada teks masalah juga ada di ``kode_konteks``. Pemanggil yang menegakkan
    syarat minimal satu konteks dan batas jumlah sumber; perakit tidak menolak apa pun.

    Args:
        session: Sesi basis data.
        sertakan_masalah: Sertakan ``masalah:`` setelah seluruh ``konteks:``.

    Returns:
        ``SumberKonteks``; daftarnya kosong bila tidak ada konteks aktif.
    """
    K = RedesainKonteksModel
    konteks = session.scalars(select(K).where(K.aktif.is_(True)).order_by(K.kode)).all()
    sumber = [
        sumber_konteks("konteks", k.id, {n: getattr(k, n) for n in FIELD_SUMBER_KONTEKS["konteks"]})
        for k in konteks
    ]
    if sertakan_masalah and konteks:
        M = RedesainMasalahModel
        rows = session.execute(
            select(M, K.kode)
            .join(K, K.id == M.konteks_id)
            .where(K.aktif.is_(True))
            .order_by(M.kode)
        ).all()
        for masalah, konteks_kode in rows:
            nilai = {n: getattr(masalah, n) for n in FIELD_SUMBER_KONTEKS["masalah"][2:]}
            nilai.update(kode=masalah.kode, konteks_kode=konteks_kode)
            sumber.append(sumber_konteks("masalah", masalah.id, nilai))
    return SumberKonteks(sumber, [k.kode for k in konteks])
