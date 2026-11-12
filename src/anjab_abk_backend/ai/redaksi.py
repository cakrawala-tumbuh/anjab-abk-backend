"""Gerbang redaksi PII dan daftar izin sumber sebelum data menyentuh model AI.

Kebijakan bawaan sengaja paling ketat (``FAIL CLOSED``): izin jenis sumber ditentukan
env ``AI_JENIS_SUMBER_DIIZINKAN`` (bawaan hanya ``SINTETIS``; operator menambah jenis
lain, mis. ``KETERANGAN_ORANG``), dan temuan PII apa pun menolak seluruh masukan.
Jenis berawalan WCP/DCS/KONSELING/MURID selalu ditolak.

Batas deteksi: nama orang di luar kamus partisipan hanya tertangkap bila muncul
tepat setelah kata konteks (``murid``, ``siswa``, ``siswi``, ``ananda``,
``orang tua``, ``wali``) dan berhuruf kapital. Tidak ada deteksi berbasis
model/NER, sehingga gerbang ini TIDAK boleh dianggap menjamin bebas PII.

Nilai PII asli tidak pernah masuk ``temuan``, ``alasan``, log, maupun galat.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings
from ..models import PartisipanModel

__all__ = [
    "HasilGerbang",
    "HasilRedaksi",
    "SumberAi",
    "gerbang_masukan",
    "muat_kamus_nama",
    "periksa_pii",
]

logger = logging.getLogger(__name__)

Alasan = Literal["SUMBER_KOSONG", "METADATA_SUMBER_HILANG", "JENIS_DITOLAK", "PII_DITEMUKAN"]

_PREFIKS_TERLARANG = ("WCP", "DCS", "KONSELING", "MURID")
_MIN_PANJANG_KATA_NAMA = 4

_RE_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+")
# Pola angka hanya cocok pada TOKEN UTUH: karakter sebelum awal bukan ``\w``/``+``/``-`` dan
# karakter sesudah akhir bukan ``\w``/``-``. Tanda hubung/spasi DI DALAM nomor tetap sah
# (``0812-3456-7890``). Tanpa batas ini deret digit di tengah id acak (UUID ber-tanda hubung,
# hex, ``ut_...``) menjadi salah-positif.
_AWAL_TOKEN = r"(?<![\w+\-])"
_AKHIR_TOKEN = r"(?![\w\-])"
_RE_NIP = re.compile(_AWAL_TOKEN + r"\d{18}" + _AKHIR_TOKEN)
_RE_NIK = re.compile(_AWAL_TOKEN + r"\d{16}" + _AKHIR_TOKEN)
_RE_TELEPON = re.compile(_AWAL_TOKEN + r"(?:\+62|62|08)(?:[ \-]?\d){8,12}" + _AKHIR_TOKEN)
_RE_MURID = re.compile(r"\b(?i:murid|siswa|siswi|ananda|orang\s+tua|wali)\s+([A-Z]\w*)")


@dataclass(frozen=True)
class SumberAi:
    """Satu sumber data calon masukan model.

    Attributes:
        source_id: Id sumber.
        source_hash: SHA-256 ``teks`` asli (heksadesimal).
        jenis: Jenis sumber, mis. ``SINTETIS``.
        teks: Isi sumber.
    """

    source_id: str
    source_hash: str
    jenis: str
    teks: str


@dataclass(frozen=True)
class HasilRedaksi:
    """Hasil ``periksa_pii``: teks tersamarkan dan jumlah temuan per kategori."""

    teks: str
    temuan: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class HasilGerbang:
    """Hasil ``gerbang_masukan``.

    Attributes:
        lolos: True bila sumber boleh diteruskan ke model.
        alasan: Alasan penolakan (``None`` bila lolos).
        sumber: Sumber dengan teks tersamarkan dan ``source_hash`` asli; ``None``
            bila ditolak.
        temuan: ``{kategori: jumlah}``; tidak pernah memuat nilai asli.
    """

    lolos: bool
    alasan: Alasan | None
    sumber: SumberAi | None
    temuan: dict[str, int] = field(default_factory=dict)


def _pola_nama(kamus_nama: list[str]) -> re.Pattern[str] | None:
    """Bangun regex nama dari frasa utuh dan tiap kata >= 4 huruf kamus."""
    kandidat: set[str] = set()
    for nama in kamus_nama:
        frasa = " ".join(nama.split())
        if not frasa:
            continue
        kandidat.add(frasa)
        kandidat.update(k for k in re.findall(r"\w+", frasa) if len(k) >= _MIN_PANJANG_KATA_NAMA)
    if not kandidat:
        return None
    alternatif = sorted(kandidat, key=len, reverse=True)
    isi = "|".join(r"\s+".join(re.escape(k) for k in a.split()) for a in alternatif)
    return re.compile(rf"(?<!\w)(?:{isi})(?!\w)", re.IGNORECASE)


def periksa_pii(teks: str, kamus_nama: list[str]) -> HasilRedaksi:
    """Samarkan PII pada ``teks`` dan hitung temuan per kategori.

    Kategori: ``EMAIL``, ``TELEPON``, ``NIK``, ``NIP``, ``NAMA_TERDAFTAR``,
    ``NAMA_MURID_KELUARGA``. Nilai yang sama dalam satu teks mendapat penanda
    stabil (``[EMAIL_1]``). Pola angka (``TELEPON``/``NIK``/``NIP``) hanya cocok pada
    token utuh, sehingga deret digit di dalam id acak (UUID, hex, ``ut_...``) tidak
    dianggap PII. Nama di luar kamus hanya tertangkap lewat pola konteks
    ``NAMA_MURID_KELUARGA``.

    Args:
        teks: Teks yang diperiksa.
        kamus_nama: Daftar nama partisipan; frasa utuh dan tiap kata >= 4 huruf
            dicocokkan tanpa peka huruf besar dengan batas kata.

    Returns:
        ``HasilRedaksi`` berisi teks tersamarkan dan ``{kategori: jumlah}`` (tanpa
        nilai asli).
    """
    temuan: dict[str, int] = {}
    penanda: dict[str, dict[str, int]] = {}

    def _ganti(kategori: str, nilai: str) -> str:
        temuan[kategori] = temuan.get(kategori, 0) + 1
        peta = penanda.setdefault(kategori, {})
        kunci = " ".join(nilai.lower().split())
        nomor = peta.setdefault(kunci, len(peta) + 1)
        return f"[{kategori}_{nomor}]"

    hasil = _RE_EMAIL.sub(lambda m: _ganti("EMAIL", m.group(0)), teks)
    hasil = _RE_NIP.sub(lambda m: _ganti("NIP", m.group(0)), hasil)
    hasil = _RE_NIK.sub(lambda m: _ganti("NIK", m.group(0)), hasil)
    hasil = _RE_TELEPON.sub(lambda m: _ganti("TELEPON", m.group(0)), hasil)

    def _murid(m: re.Match[str]) -> str:
        awal = m.start(1) - m.start(0)
        return m.group(0)[:awal] + _ganti("NAMA_MURID_KELUARGA", m.group(1))

    hasil = _RE_MURID.sub(_murid, hasil)
    pola = _pola_nama(kamus_nama)
    if pola is not None:
        hasil = pola.sub(lambda m: _ganti("NAMA_TERDAFTAR", m.group(0)), hasil)
    return HasilRedaksi(teks=hasil, temuan=temuan)


def _jenis_diizinkan(jenis: str, settings: Settings) -> bool:
    """Jenis lolos bila tercantum di daftar izin dan tidak berawalan terlarang (PRM:6)."""
    norm = jenis.strip().upper()
    if not norm or norm.startswith(_PREFIKS_TERLARANG):
        return False
    return norm in {j.strip().upper() for j in settings.ai_jenis_sumber_diizinkan}


def _tolak(alasan: Alasan, sumber: SumberAi | None, temuan: dict[str, int] | None = None):
    """Catat penolakan (hanya id, alasan, hitungan) dan bentuk hasilnya."""
    logger.warning(
        "ai_gerbang_ditolak",
        extra={
            "alasan": alasan,
            "source_id": sumber.source_id if sumber else None,
            "temuan": temuan or {},
        },
    )
    return HasilGerbang(lolos=False, alasan=alasan, sumber=None, temuan=temuan or {})


def gerbang_masukan(
    sumber: SumberAi | None, kamus_nama: list[str], settings: Settings
) -> HasilGerbang:
    """Tentukan apakah ``sumber`` boleh diteruskan ke model.

    Urutan pemeriksaan: ``SUMBER_KOSONG`` (sumber ``None`` atau teks kosong),
    ``METADATA_SUMBER_HILANG`` (id/hash kosong atau hash bukan SHA-256 ``teks``),
    ``JENIS_DITOLAK`` (jenis tidak di ``AI_JENIS_SUMBER_DIIZINKAN``, atau berawalan
    ``WCP``/``DCS``/``KONSELING``/``MURID`` walau tercantum), lalu
    ``PII_DITEMUKAN``. Mode ``BLOKIR`` menolak temuan apa pun; ``SAMARKAN``
    meloloskan dengan teks tersamarkan kecuali ada ``NAMA_MURID_KELUARGA``, yang
    selalu memblok.

    Args:
        sumber: Sumber yang diperiksa.
        kamus_nama: Kamus nama partisipan (lihat ``muat_kamus_nama``).
        settings: Pengaturan aplikasi (``ai_jenis_sumber_diizinkan``, ``ai_pii_mode``).

    Returns:
        ``HasilGerbang``. ``sumber`` hanya terisi bila lolos (teks tersamarkan,
        ``source_hash`` asli).
    """
    if sumber is None or not sumber.teks.strip():
        return _tolak("SUMBER_KOSONG", sumber)
    hash_teks = hashlib.sha256(sumber.teks.encode("utf-8")).hexdigest()
    if not sumber.source_id.strip() or sumber.source_hash.strip().lower() != hash_teks:
        return _tolak("METADATA_SUMBER_HILANG", sumber)
    if not _jenis_diizinkan(sumber.jenis, settings):
        return _tolak("JENIS_DITOLAK", sumber)
    hasil = periksa_pii(sumber.teks, kamus_nama)
    if hasil.temuan and (settings.ai_pii_mode == "BLOKIR" or "NAMA_MURID_KELUARGA" in hasil.temuan):
        return _tolak("PII_DITEMUKAN", sumber, hasil.temuan)
    bersih = SumberAi(
        source_id=sumber.source_id,
        source_hash=sumber.source_hash,
        jenis=sumber.jenis,
        teks=hasil.teks,
    )
    return HasilGerbang(lolos=True, alasan=None, sumber=bersih, temuan=hasil.temuan)


def muat_kamus_nama(session: Session) -> list[str]:
    """Muat nama seluruh partisipan (aktif maupun nonaktif) sebagai kamus redaksi.

    Args:
        session: Sesi SQLAlchemy.

    Returns:
        Daftar nama unik, terurut, tanpa entri kosong.
    """
    nama = session.scalars(select(PartisipanModel.nama)).all()
    return sorted({n.strip() for n in nama if n and n.strip()})
