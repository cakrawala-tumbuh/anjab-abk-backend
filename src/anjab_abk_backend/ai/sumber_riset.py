"""Perakit sumber riset untuk fungsi AI P08 (sintesis bukti riset).

Satu protokol riset dirangkai menjadi daftar ``SumberAi`` berjenis ``RISET``: protokol itu
sendiri (``protokol:<id>``), statistiknya yang ``TERVERIFIKASI`` (``statistik:<id>``), kasus
negatifnya (``kasus-negatif:<id>``), dan seluruh log versi metode ``redesain_versi_metode``
(``versi-metode:<id>``) sebagai ``version_log``.

Batas isi:

- Statistik ``DRAF`` tidak pernah dirakit.
- Identitas orang tidak dikirim: ``dibuat_oleh``, ``dikunci_oleh``, ``diverifikasi_oleh``, dan
  ``pemeriksa_pemutus`` sengaja tidak ada di ``FIELD_SUMBER_RISET``.
- Field panjang (``isi`` protokol, ``keluaran`` statistik) dikirim apa adanya sebagai blok agar
  tabel keluaran analisis tidak rusak; field lain satu baris dengan spasi beruntun dirapatkan.

Jenis ``RISET`` baru boleh sampai ke model bila operator mencantumkannya di
``AI_JENIS_SUMBER_DIIZINKAN`` (keputusan aktivasi, bukan bawaan). Modul ini hanya membaca.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    RedesainVersiMetodeModel,
    RisetKasusNegatifModel,
    RisetProtokolModel,
    RisetStatistikModel,
)
from ..schemas.riset_statistik import StatusStatistik
from .redaksi import SumberAi

__all__ = [
    "AWALAN_SUMBER_RISET",
    "FIELD_SUMBER_RISET",
    "JENIS_SUMBER_RISET",
    "jumlah_statistik_terverifikasi",
    "rakit_sumber_riset",
    "sumber_riset",
    "teks_sumber_riset",
]

JENIS_SUMBER_RISET = "RISET"
"""Jenis sumber data riset. Baru boleh dikirim ke model bila operator mencantumkannya di
``AI_JENIS_SUMBER_DIIZINKAN`` (keputusan aktivasi, bukan bawaan)."""

AWALAN_SUMBER_RISET = ("protokol:", "statistik:", "kasus-negatif:", "versi-metode:")
"""Awalan ``source_id`` yang dihasilkan modul ini, satu per tabel sumber."""

FIELD_SUMBER_RISET: dict[str, tuple[str, ...]] = {
    "protokol": ("kode", "versi", "isi_hash", "isi"),
    "statistik": ("nama_analisis", "kode_sumber_ref", "keluaran"),
    "kasus-negatif": ("ringkasan", "alasan_negatif", "sumber_ref"),
    "versi-metode": (
        "versi",
        "tanggal",
        "bagian",
        "apa_diperbarui",
        "alasan_risiko",
        "status_hasil_uji",
    ),
}
"""Satu-satunya kunci yang boleh muncul pada teks sumber per jenis baris."""

_FIELD_BLOK = frozenset({"isi", "keluaran"})
"""Field yang dikirim apa adanya (multi-baris) sebagai blok ``kunci:\\n<nilai>``."""


def teks_sumber_riset(tabel: str, nilai: dict[str, Any]) -> str:
    """Susun teks sumber satu baris riset dari kunci yang diizinkan untuk tabelnya.

    Hanya kunci di ``FIELD_SUMBER_RISET[tabel]`` yang dipakai, dalam urutan tetap. Field di
    ``_FIELD_BLOK`` ditulis ``kunci:`` lalu nilainya apa adanya di baris berikut; field lain
    ``kunci: nilai`` satu baris dengan spasi beruntun dirapatkan. Nilai ``None`` atau string
    kosong dilewati; kunci lain pada ``nilai`` diabaikan sehingga tidak pernah ikut terkirim.

    Args:
        tabel: Jenis baris (kunci ``FIELD_SUMBER_RISET``).
        nilai: Pemetaan nama field ke nilai.

    Returns:
        Teks deterministik untuk baris itu.

    Raises:
        KeyError: ``tabel`` tidak dikenal.
    """
    baris = []
    for kunci in FIELD_SUMBER_RISET[tabel]:
        isi = nilai.get(kunci)
        if isi is None or (isinstance(isi, str) and not isi.strip()):
            continue
        if kunci in _FIELD_BLOK:
            baris.append(f"{kunci}:\n{isi}")
        else:
            baris.append(f"{kunci}: {' '.join(str(isi).split())}")
    return "\n".join(baris)


def sumber_riset(tabel: str, baris_id: str, nilai: dict[str, Any]) -> SumberAi:
    """Bungkus satu baris riset sebagai ``SumberAi`` berjenis ``RISET``.

    Args:
        tabel: Jenis baris (``protokol``, ``statistik``, ``kasus-negatif``, ``versi-metode``);
            menjadi awalan ``source_id``.
        baris_id: Id baris di tabelnya.
        nilai: Field baris (lihat ``teks_sumber_riset``).

    Returns:
        Sumber dengan ``source_id`` ``<tabel>:<baris_id>`` dan ``source_hash`` SHA-256 teksnya.
    """
    teks = teks_sumber_riset(tabel, nilai)
    return SumberAi(
        source_id=f"{tabel}:{baris_id}",
        source_hash=hashlib.sha256(teks.encode("utf-8")).hexdigest(),
        jenis=JENIS_SUMBER_RISET,
        teks=teks,
    )


def _kolom(rec: Any, tabel: str) -> dict[str, Any]:
    """Ambil atribut ``FIELD_SUMBER_RISET[tabel]`` dari satu objek ORM menjadi dict."""
    return {n: getattr(rec, n) for n in FIELD_SUMBER_RISET[tabel]}


def jumlah_statistik_terverifikasi(session: Session, protokol_id: str) -> int:
    """Hitung statistik ``TERVERIFIKASI`` milik satu protokol riset.

    Args:
        session: Sesi basis data.
        protokol_id: Id ``riset_protokol``.

    Returns:
        Jumlah baris ``riset_statistik`` protokol itu yang berstatus ``TERVERIFIKASI``.
    """
    return len(_statistik_terverifikasi(session, protokol_id))


def _statistik_terverifikasi(session: Session, protokol_id: str) -> list[RisetStatistikModel]:
    """Statistik ``TERVERIFIKASI`` satu protokol, urut ``created_at`` lalu ``id``."""
    stmt = (
        select(RisetStatistikModel)
        .where(
            RisetStatistikModel.protokol_id == protokol_id,
            RisetStatistikModel.status == StatusStatistik.TERVERIFIKASI.value,
        )
        .order_by(RisetStatistikModel.created_at, RisetStatistikModel.id)
    )
    return list(session.scalars(stmt))


def rakit_sumber_riset(session: Session, protokol: RisetProtokolModel) -> list[SumberAi]:
    """Rangkai satu protokol riset beserta bukti turunannya menjadi sumber AI ``RISET``.

    Urutan tetap: ``protokol:<id>``, lalu statistik ``TERVERIFIKASI`` protokol itu, kasus negatif
    protokol itu, dan seluruh baris ``redesain_versi_metode``; masing-masing urut waktu lalu id.
    Statistik ``DRAF`` tidak pernah ikut. Pemanggil yang memastikan protokol ``TERKUNCI``.

    Args:
        session: Sesi basis data.
        protokol: Baris ``riset_protokol`` sasaran.

    Returns:
        Daftar sumber; elemen pertama selalu protokol itu.
    """
    sumber = [sumber_riset("protokol", protokol.id, _kolom(protokol, "protokol"))]
    for stat in _statistik_terverifikasi(session, protokol.id):
        sumber.append(sumber_riset("statistik", stat.id, _kolom(stat, "statistik")))
    kasus = session.scalars(
        select(RisetKasusNegatifModel)
        .where(RisetKasusNegatifModel.protokol_id == protokol.id)
        .order_by(RisetKasusNegatifModel.created_at, RisetKasusNegatifModel.id)
    )
    for k in kasus:
        sumber.append(sumber_riset("kasus-negatif", k.id, _kolom(k, "kasus-negatif")))
    versi = session.scalars(
        select(RedesainVersiMetodeModel).order_by(
            RedesainVersiMetodeModel.tanggal, RedesainVersiMetodeModel.id
        )
    )
    for v in versi:
        sumber.append(sumber_riset("versi-metode", v.id, _kolom(v, "versi-metode")))
    return sumber
