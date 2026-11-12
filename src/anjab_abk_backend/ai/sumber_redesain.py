"""Perakit sumber redesain bersama untuk fungsi AI P05, P06, dan P07.

Satu masalah redesain dirangkai menjadi daftar ``SumberAi`` berjenis ``REDESAIN``: masalah itu
sendiri, proses dan langkah ALUR-nya, bukti, koreksi langkah, dan (opsional) konfirmasi sekolah.
Tiap sumber satu baris tabel, ``source_id`` berawalan nama tabelnya (``masalah:``, ``proses:``,
``langkah:``, ``bukti:``, ``koreksi:``, ``konfirmasi:``) diikuti id baris. Alternatif redesain
(``alternatif:``, dipakai P06 dan P07) dirakit terpisah lewat ``rakit_sumber_alternatif``, dan
kesiapan tiap penerima alternatif pada satu periode (``kesiapan:``) lewat
``rakit_sumber_kesiapan``.

Batas isi:

- Teks hanya memuat field isi dan status; orang hanya muncul lewat kode samaran yang sudah ada
  (``*_kode_orang``/``kode_orang``), tidak pernah lewat nama atau id partisipan.
- Konfirmasi hanya yang sudah ``dikirim_pada`` (KAI:15: pernyataan awal diperoleh netral lebih
  dulu); ``cerita_sebelum`` dan ``catatan_akses`` tidak pernah disertakan. Koreksi yang ditulis
  lewat konfirmasi mengikuti aturan yang sama.
- ``catatan_privasi_gap`` bukti tidak disertakan.

Jenis ``REDESAIN`` baru boleh sampai ke model bila operator mencantumkannya di
``AI_JENIS_SUMBER_DIIZINKAN`` (keputusan aktivasi, bukan bawaan). Modul ini hanya membaca.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from ..models import (
    RedesainAlternatifModel,
    RedesainAlternatifPenerimaModel,
    RedesainBuktiModel,
    RedesainKesiapanModel,
    RedesainKonfirmasiModel,
    RedesainKoreksiLangkahModel,
    RedesainLangkahModel,
    RedesainMasalahModel,
    RedesainMasalahUraianTugasModel,
    RedesainProsesModel,
    SekolahModel,
    TiUraianTugasModel,
)
from ..redesain.schemas.alternatif import EstimasiDelta, StatusKesiapan
from ..redesain.services.alternatif import hitung_status_opsi
from .redaksi import SumberAi

__all__ = [
    "AWALAN_SUMBER_REDESAIN",
    "FIELD_SUMBER_REDESAIN",
    "JENIS_SUMBER_REDESAIN",
    "STATUS_BELUM_DINILAI",
    "proses_terhubung",
    "rakit_sumber_alternatif",
    "rakit_sumber_kesiapan",
    "rakit_sumber_redesain",
    "sumber_redesain",
    "teks_sumber_redesain",
]

JENIS_SUMBER_REDESAIN = "REDESAIN"
"""Jenis sumber data redesain. Baru boleh dikirim ke model bila operator mencantumkannya di
``AI_JENIS_SUMBER_DIIZINKAN`` (keputusan aktivasi, bukan bawaan)."""

AWALAN_SUMBER_REDESAIN = (
    "masalah:",
    "proses:",
    "langkah:",
    "bukti:",
    "koreksi:",
    "konfirmasi:",
    "alternatif:",
    "kesiapan:",
)
"""Awalan ``source_id`` yang dihasilkan modul ini, satu per tabel sumber."""

FIELD_SUMBER_REDESAIN: dict[str, tuple[str, ...]] = {
    "masalah": (
        "kode",
        "periode_acuan",
        "rumusan_hipotesis",
        "sumber_awal_keterbatasan",
        "status_awal",
        "gelombang",
        "penjelasan_alternatif",
        "keterangan_sekolah",
        "pic_kode_orang",
        "task_links",
    ),
    "proses": ("kode", "masalah_kode", "sekolah", "periode", "nama_proses"),
    "langkah": (
        "kode",
        "proses_kode",
        "urutan",
        "tahap",
        "pemicu_input",
        "pelaksana",
        "pekerjaan_sistem",
        "keluaran_penerima",
        "pemeriksa_pemutus",
        "hambatan",
        "status_langkah",
    ),
    "bukti": (
        "kode",
        "langkah_kode",
        "unit_periode",
        "jenis",
        "pembuat_kode_orang",
        "pembuat_peran",
        "independen",
        "klaim_didukung",
        "klaim_tidak_didukung",
        "tanggal_versi_lokasi",
        "status_pemeriksaan",
        "pemeriksa_kode_orang",
        "alasan",
    ),
    "koreksi": ("langkah_kode", "kode_orang", "isi", "waktu"),
    "konfirmasi": (
        "kode_orang",
        "peran",
        "sumber",
        "tanggal",
        "kesesuaian",
        "koreksi",
        "masalah_baru",
        "alasan_k",
        "bukti_dapat_diperiksa",
        "hal_belum_jelas",
        "catatan_independensi",
        "k1",
        "k2",
        "k3",
        "k4",
        "indikasi_risiko",
        "status",
    ),
    "alternatif": (
        "opsi",
        "pihak_penerima_jabatan_id",
        "komitmen_penerima",
        "jadwal_puncak",
        "keterampilan_akses",
        "tambahan_bersih",
        "gap_penerima",
        "risiko_layanan",
    ),
    "kesiapan": (
        "kode_alternatif",
        "penerima_jabatan_id",
        "material",
        "periode",
        "status",
        "delta_asal",
        "delta_penerima",
        "delta_organisasi",
        "syarat",
        "alasan_hold",
        "status_opsi",
    ),
}
"""Satu-satunya kunci yang boleh muncul pada teks sumber per tabel. ``cerita_sebelum``,
``catatan_akses``, dan ``catatan_privasi_gap`` sengaja tidak ada."""


STATUS_BELUM_DINILAI = "BELUM_DINILAI"
"""Nilai ``status`` sumber ``kesiapan:`` bila penerima belum punya penilaian pada periode itu."""


def teks_sumber_redesain(tabel: str, nilai: dict[str, Any]) -> str:
    """Susun teks sumber satu baris redesain dari kunci yang diizinkan untuk tabelnya.

    Hanya kunci di ``FIELD_SUMBER_REDESAIN[tabel]`` yang dipakai, dalam urutan tetap, satu baris
    ``kunci: nilai`` per field; spasi beruntun dirapatkan, nilai ``None`` atau string kosong
    dilewati. Kunci lain pada ``nilai`` diabaikan sehingga tidak pernah ikut terkirim.

    Args:
        tabel: Nama tabel sumber tanpa awalan ``redesain_`` (kunci ``FIELD_SUMBER_REDESAIN``).
        nilai: Pemetaan nama field ke nilai.

    Returns:
        Teks deterministik untuk baris itu.

    Raises:
        KeyError: ``tabel`` tidak dikenal.
    """
    baris = []
    for kunci in FIELD_SUMBER_REDESAIN[tabel]:
        isi = nilai.get(kunci)
        if isi is None or (isinstance(isi, str) and not isi.strip()):
            continue
        baris.append(f"{kunci}: {' '.join(str(isi).split())}")
    return "\n".join(baris)


def sumber_redesain(tabel: str, baris_id: str, nilai: dict[str, Any]) -> SumberAi:
    """Bungkus satu baris redesain sebagai ``SumberAi`` berjenis ``REDESAIN``.

    Args:
        tabel: Nama tabel sumber (``masalah``, ``proses``, ``langkah``, ``bukti``, ``koreksi``,
            ``konfirmasi``, atau ``alternatif``); menjadi awalan ``source_id``.
        baris_id: Id baris di tabelnya.
        nilai: Field baris (lihat ``teks_sumber_redesain``).

    Returns:
        Sumber dengan ``source_id`` ``<tabel>:<baris_id>`` dan ``source_hash`` SHA-256 teksnya.
    """
    teks = teks_sumber_redesain(tabel, nilai)
    return SumberAi(
        source_id=f"{tabel}:{baris_id}",
        source_hash=hashlib.sha256(teks.encode("utf-8")).hexdigest(),
        jenis=JENIS_SUMBER_REDESAIN,
        teks=teks,
    )


def proses_terhubung(session: Session, masalah_id: str) -> bool:
    """Cek syarat MX:10: masalah punya minimal satu proses yang memiliki minimal satu langkah.

    Args:
        session: Sesi basis data.
        masalah_id: Id ``redesain_masalah``.

    Returns:
        ``True`` bila ada ``redesain_proses`` milik masalah itu dengan >= 1 ``redesain_langkah``.
    """
    stmt = select(
        exists()
        .where(RedesainProsesModel.masalah_id == masalah_id)
        .where(RedesainLangkahModel.proses_id == RedesainProsesModel.id)
    )
    return bool(session.scalar(stmt))


def _kolom(rec: Any, nama: Iterable[str]) -> dict[str, Any]:
    """Ambil atribut ``nama`` dari satu objek ORM menjadi dict (hanya kolom yang diminta)."""
    return {n: getattr(rec, n) for n in nama}


def rakit_sumber_redesain(
    session: Session, masalah_id: str, *, sertakan_konfirmasi: bool
) -> list[SumberAi]:
    """Rangkai satu masalah redesain beserta data turunannya menjadi sumber AI ``REDESAIN``.

    Urutan tetap: ``masalah:`` (dengan ``task_links`` uraian tugas tertaut), lalu ``proses:``
    (urut ``kode``) masing-masing diikuti ``langkah:`` (urut ``urutan``, lalu ``kode``), lalu
    ``bukti:`` (urut ``kode``), ``koreksi:`` (urut ``waktu``, lalu ``id``), dan bila diminta
    ``konfirmasi:`` (urut ``dikirim_pada``, lalu ``id``). Pemanggil yang menegakkan batas jumlah
    sumber dan syarat proses terhubung; perakit tidak menolak apa pun.

    Konfirmasi hanya yang ``dikirim_pada`` terisi. Koreksi ikut bila ditulis Tim Kajian
    (``konfirmasi_id`` kosong), atau bila ``sertakan_konfirmasi`` dan konfirmasinya sudah
    terkirim.

    Args:
        session: Sesi basis data.
        masalah_id: Id ``redesain_masalah``.
        sertakan_konfirmasi: Sertakan konfirmasi sekolah terkirim dan koreksi yang ditulis lewat
            konfirmasi itu.

    Returns:
        Daftar sumber; kosong bila masalah tidak ada.
    """
    masalah = session.get(RedesainMasalahModel, masalah_id)
    if masalah is None:
        return []
    tautan = session.execute(
        select(TiUraianTugasModel.id, TiUraianTugasModel.uraian)
        .join(
            RedesainMasalahUraianTugasModel,
            RedesainMasalahUraianTugasModel.uraian_tugas_id == TiUraianTugasModel.id,
        )
        .where(RedesainMasalahUraianTugasModel.masalah_id == masalah_id)
        .order_by(TiUraianTugasModel.id)
    ).all()
    nilai_masalah = _kolom(masalah, FIELD_SUMBER_REDESAIN["masalah"][:-1])
    nilai_masalah["task_links"] = "; ".join(f"{uid} ({uraian})" for uid, uraian in tautan)
    hasil = [sumber_redesain("masalah", masalah.id, nilai_masalah)]

    proses_rows = session.execute(
        select(RedesainProsesModel, SekolahModel.nama)
        .outerjoin(SekolahModel, SekolahModel.id == RedesainProsesModel.sekolah_id)
        .where(RedesainProsesModel.masalah_id == masalah_id)
        .order_by(RedesainProsesModel.kode)
    ).all()
    kode_langkah: dict[str, str] = {}
    for proses, sekolah_nama in proses_rows:
        nilai = _kolom(proses, ("kode", "periode", "nama_proses"))
        nilai.update(masalah_kode=masalah.kode, sekolah=sekolah_nama)
        hasil.append(sumber_redesain("proses", proses.id, nilai))
        langkah_rows = session.scalars(
            select(RedesainLangkahModel)
            .where(RedesainLangkahModel.proses_id == proses.id)
            .order_by(RedesainLangkahModel.urutan, RedesainLangkahModel.kode)
        ).all()
        for langkah in langkah_rows:
            kode_langkah[langkah.id] = langkah.kode
            nilai = _kolom(langkah, FIELD_SUMBER_REDESAIN["langkah"][2:])
            nilai.update(kode=langkah.kode, proses_kode=proses.kode)
            hasil.append(sumber_redesain("langkah", langkah.id, nilai))

    for bukti in session.scalars(
        select(RedesainBuktiModel)
        .where(RedesainBuktiModel.masalah_id == masalah_id)
        .order_by(RedesainBuktiModel.kode)
    ).all():
        nilai = _kolom(bukti, FIELD_SUMBER_REDESAIN["bukti"][2:])
        nilai.update(kode=bukti.kode, langkah_kode=kode_langkah.get(bukti.langkah_id or ""))
        hasil.append(sumber_redesain("bukti", bukti.id, nilai))

    if kode_langkah:
        K = RedesainKoreksiLangkahModel
        boleh = K.konfirmasi_id.is_(None)
        if sertakan_konfirmasi:
            terkirim = select(RedesainKonfirmasiModel.id).where(
                RedesainKonfirmasiModel.dikirim_pada.is_not(None)
            )
            boleh = or_(boleh, and_(K.konfirmasi_id.is_not(None), K.konfirmasi_id.in_(terkirim)))
        for koreksi in session.scalars(
            select(K).where(K.langkah_id.in_(list(kode_langkah)), boleh).order_by(K.waktu, K.id)
        ).all():
            nilai = _kolom(koreksi, ("kode_orang", "isi", "waktu"))
            nilai["langkah_kode"] = kode_langkah[koreksi.langkah_id]
            hasil.append(sumber_redesain("koreksi", koreksi.id, nilai))

    if sertakan_konfirmasi:
        for konfirmasi in session.scalars(
            select(RedesainKonfirmasiModel)
            .where(
                RedesainKonfirmasiModel.masalah_id == masalah_id,
                RedesainKonfirmasiModel.dikirim_pada.is_not(None),
            )
            .order_by(RedesainKonfirmasiModel.dikirim_pada, RedesainKonfirmasiModel.id)
        ).all():
            nilai = _kolom(konfirmasi, FIELD_SUMBER_REDESAIN["konfirmasi"])
            hasil.append(sumber_redesain("konfirmasi", konfirmasi.id, nilai))
    return hasil


def rakit_sumber_alternatif(session: Session, masalah_id: str) -> list[SumberAi]:
    """Rangkai tiap ``redesain_alternatif`` satu masalah menjadi sumber AI ``REDESAIN``.

    Satu sumber per alternatif, ``source_id`` ``alternatif:<id>``, urut ``kode``. Teks hanya
    memuat field ``FIELD_SUMBER_REDESAIN["alternatif"]`` (opsi, penerima berupa id jabatan,
    komitmen, jadwal puncak, keterampilan/akses, tambahan bersih, gap, risiko layanan); status
    telaah, keputusan, dan pemutus tidak pernah ikut, sehingga model tidak membaca putusan Tim.

    Args:
        session: Sesi basis data.
        masalah_id: Id ``redesain_masalah``.

    Returns:
        Daftar sumber; kosong bila masalah tidak punya alternatif.
    """
    return [
        sumber_redesain("alternatif", alt.id, _kolom(alt, FIELD_SUMBER_REDESAIN["alternatif"]))
        for alt in session.scalars(
            select(RedesainAlternatifModel)
            .where(RedesainAlternatifModel.masalah_id == masalah_id)
            .order_by(RedesainAlternatifModel.kode)
        ).all()
    ]


def _teks_delta(jam: Any, estimasi: str) -> str:
    """Tulis satu delta kesiapan: ``NOT_ESTIMABLE`` apa adanya, atau jam beserta penandanya."""
    if estimasi == EstimasiDelta.NOT_ESTIMABLE or jam is None:
        return EstimasiDelta.NOT_ESTIMABLE.value
    return f"{jam} jam kerja efektif per periode ({estimasi})"


def rakit_sumber_kesiapan(session: Session, masalah_id: str, periode: str) -> list[SumberAi]:
    """Rangkai kesiapan tiap penerima alternatif satu masalah pada satu periode menjadi sumber AI.

    Satu sumber per pasangan alternatif x penerima, ``source_id``
    ``kesiapan:<alternatif_id>:<penerima_id>``, urut ``kode`` alternatif lalu ``created_at`` dan
    ``id`` penerima. Teks memuat ``kode`` alternatif, ``penerima_jabatan_id``, ``material``,
    ``periode``, status penilaian terakhir (``created_at``, ``id``) pada periode itu atau
    ``BELUM_DINILAI``, ketiga delta (``NOT_ESTIMABLE`` ditulis apa adanya, tidak pernah sebagai
    nol), ``syarat``/``alasan_hold``, dan ``status_opsi`` alternatif (``hitung_status_opsi``).
    Hanya kode dan id yang muncul, tidak ada nama orang. Penilaian periode lain tidak ikut.

    Args:
        session: Sesi basis data.
        masalah_id: Id ``redesain_masalah``.
        periode: Periode kesiapan yang diminta (mis. ``2026/27``).

    Returns:
        Daftar sumber; kosong bila masalah tidak punya alternatif ber-penerima.
    """
    hasil: list[SumberAi] = []
    alternatif = session.scalars(
        select(RedesainAlternatifModel)
        .where(RedesainAlternatifModel.masalah_id == masalah_id)
        .order_by(RedesainAlternatifModel.kode)
    ).all()
    for alt in alternatif:
        penerima = session.scalars(
            select(RedesainAlternatifPenerimaModel)
            .where(RedesainAlternatifPenerimaModel.alternatif_id == alt.id)
            .order_by(
                RedesainAlternatifPenerimaModel.created_at, RedesainAlternatifPenerimaModel.id
            )
        ).all()
        if not penerima:
            continue
        terakhir: dict[str, RedesainKesiapanModel] = {}
        for nilai in session.scalars(
            select(RedesainKesiapanModel)
            .where(
                RedesainKesiapanModel.penerima_id.in_([p.id for p in penerima]),
                RedesainKesiapanModel.periode == periode,
            )
            .order_by(RedesainKesiapanModel.created_at, RedesainKesiapanModel.id)
        ).all():
            terakhir[nilai.penerima_id] = nilai
        status_opsi = hitung_status_opsi(
            (
                p.material,
                StatusKesiapan(terakhir[p.id].status) if p.id in terakhir else None,
            )
            for p in penerima
        )
        for p in penerima:
            n = terakhir.get(p.id)
            isi: dict[str, Any] = {
                "kode_alternatif": alt.kode,
                "penerima_jabatan_id": p.penerima_jabatan_id,
                "material": "ya" if p.material else "tidak",
                "periode": periode,
                "status": n.status if n else STATUS_BELUM_DINILAI,
                "status_opsi": status_opsi.value,
            }
            if n:
                isi.update(
                    delta_asal=_teks_delta(n.delta_asal_jam, n.delta_asal_estimasi),
                    delta_penerima=_teks_delta(n.delta_penerima_jam, n.delta_penerima_estimasi),
                    delta_organisasi=_teks_delta(
                        n.delta_organisasi_jam, n.delta_organisasi_estimasi
                    ),
                    syarat=n.syarat,
                    alasan_hold=n.alasan_hold,
                )
            hasil.append(sumber_redesain("kesiapan", f"{alt.id}:{p.id}", isi))
    return hasil
