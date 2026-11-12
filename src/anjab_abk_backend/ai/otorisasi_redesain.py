"""Cuplikan status otorisasi (``authorization_state``) satu masalah redesain, milik server.

Kartu keputusan P07 (library prompt YPII, PRM:48-52) mendahului tanda tangan: AI menyusun, Tim
memvalidasi, Yayasan menandatangani PRIORITY dan CHANGE terpisah (I07:68). Agar kartu tidak
pernah dibaca sebagai izin perubahan (KTK:139), status otorisasinya **tidak** berasal dari model:
server membacanya dari ``redesain_alternatif`` (status telaah, pemutus, keputusan, prasyarat
monitoring) dan ``redesain_penilaian.prioritas_final`` saat pengajuan, lalu menyimpannya di
``ai_usulan.konteks_server``. Model hanya menerima salinan bacaannya sebagai satu sumber
``otorisasi:<masalah_id>``. Modul ini hanya membaca.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    RedesainAlternatifModel,
    RedesainKeputusanPerubahanModel,
    RedesainPenilaianModel,
)
from .redaksi import SumberAi
from .sumber_redesain import JENIS_SUMBER_REDESAIN

__all__ = [
    "AWALAN_SUMBER_OTORISASI",
    "KEPUTUSAN_BELUM_DIPUTUS",
    "SUMBER_STATE_SERVER",
    "bangun_authorization_state",
    "sumber_otorisasi",
]

AWALAN_SUMBER_OTORISASI = "otorisasi:"
"""Awalan ``source_id`` cuplikan otorisasi: ``otorisasi:<masalah_id>``."""

KEPUTUSAN_BELUM_DIPUTUS = "BELUM_DIPUTUS"
"""Nilai ``keputusan`` pada ``keputusan_perubahan`` bila alternatif belum punya keputusan
perubahan pada periode yang diminta."""

SUMBER_STATE_SERVER = "server"
"""Nilai tetap ``authorization_state.sumber``: penanda bahwa cuplikan diisi server."""


def _sekarang() -> datetime:
    """Waktu pengambilan cuplikan (UTC aware); dipisah agar tes dapat membekukan jam."""
    return datetime.now(UTC)


def bangun_authorization_state(
    session: Session, masalah_id: str, periode: str | None = None
) -> dict[str, Any]:
    """Susun cuplikan status otorisasi satu masalah dari basis data saat ini.

    Satu entri per ``redesain_alternatif`` masalah itu, urut ``kode`` (sama dengan
    ``rakit_sumber_alternatif``). ``change_ditandatangani`` selalu ``False`` karena aplikasi
    belum punya model tanda tangan CHANGE (butir 14/16/17 di luar lingkup).

    Bila ``periode`` diberikan, ditambah ``keputusan_perubahan`` (sejajar ``alternatif``): keputusan
    perubahan (ChangeDecision) **terakhir** (``created_at``, ``id``) tiap alternatif pada periode
    itu, atau ``keputusan`` ``BELUM_DIPUTUS`` bila belum ada. Ia terpisah dari ``prioritas_final``.

    Args:
        session: Sesi basis data.
        masalah_id: Id ``redesain_masalah``.
        periode: Periode keputusan perubahan; ``None`` melewatkan ``keputusan_perubahan``.

    Returns:
        ``{"alternatif": [{alternatif_id, status_telaah, pemutus_kode_orang, keputusan,
        prasyarat_monitoring}], "prioritas_final", "change_ditandatangani": False,
        "sumber": "server", "diambil_pada"}``; ``prioritas_final`` null bila belum ada
        penilaian atau belum diputuskan, ``diambil_pada`` waktu ISO 8601 UTC.

    Example:
        >>> bangun_authorization_state(session, masalah_id)["sumber"]  # doctest: +SKIP
        'server'
    """
    daftar_alt = session.scalars(
        select(RedesainAlternatifModel)
        .where(RedesainAlternatifModel.masalah_id == masalah_id)
        .order_by(RedesainAlternatifModel.kode)
    ).all()
    alternatif = [
        {
            "alternatif_id": alt.id,
            "status_telaah": alt.status_telaah,
            "pemutus_kode_orang": alt.pemutus_kode_orang,
            "keputusan": alt.keputusan,
            "prasyarat_monitoring": alt.prasyarat_monitoring,
        }
        for alt in daftar_alt
    ]
    prioritas_final = session.scalar(
        select(RedesainPenilaianModel.prioritas_final).where(
            RedesainPenilaianModel.masalah_id == masalah_id
        )
    )
    state: dict[str, Any] = {
        "alternatif": alternatif,
        "prioritas_final": prioritas_final,
        "change_ditandatangani": False,
        "sumber": SUMBER_STATE_SERVER,
        "diambil_pada": _sekarang().isoformat(),
    }
    if periode is not None:
        state["keputusan_perubahan"] = _keputusan_perubahan(session, daftar_alt, periode)
    return state


def _keputusan_perubahan(
    session: Session, daftar_alt: list[RedesainAlternatifModel], periode: str
) -> list[dict[str, Any]]:
    """Keputusan perubahan terakhir tiap alternatif pada ``periode``, atau ``BELUM_DIPUTUS``."""
    terakhir: dict[str, RedesainKeputusanPerubahanModel] = {}
    if daftar_alt:
        K = RedesainKeputusanPerubahanModel
        for k in session.scalars(
            select(K)
            .where(K.alternatif_id.in_([a.id for a in daftar_alt]), K.periode == periode)
            .order_by(K.created_at, K.id)
        ).all():
            terakhir[k.alternatif_id] = k
    return [
        {
            "alternatif_id": alt.id,
            "periode": periode,
            "keputusan": terakhir[alt.id].keputusan
            if alt.id in terakhir
            else KEPUTUSAN_BELUM_DIPUTUS,
            "status_opsi_saat_putus": terakhir[alt.id].status_opsi_saat_putus
            if alt.id in terakhir
            else None,
        }
        for alt in daftar_alt
    ]


def sumber_otorisasi(masalah_id: str, state: dict[str, Any]) -> SumberAi:
    """Bungkus cuplikan otorisasi sebagai sumber AI ``REDESAIN`` (``otorisasi:<masalah_id>``).

    Teksnya JSON kanonik (kunci terurut, ``ensure_ascii=False``, tanpa spasi pemisah) dari
    ``state`` tanpa ``diambil_pada``, sehingga hash hanya berubah bila isi otorisasinya berubah.
    Sumber ini tetap melewati gerbang jenis dan PII gateway seperti sumber redesain lain.

    Args:
        masalah_id: Id ``redesain_masalah``.
        state: Hasil ``bangun_authorization_state``.

    Returns:
        Sumber dengan ``source_hash`` SHA-256 teksnya.
    """
    isi = {k: v for k, v in state.items() if k != "diambil_pada"}
    teks = json.dumps(isi, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return SumberAi(
        source_id=f"{AWALAN_SUMBER_OTORISASI}{masalah_id}",
        source_hash=hashlib.sha256(teks.encode("utf-8")).hexdigest(),
        jenis=JENIS_SUMBER_REDESAIN,
        teks=teks,
    )
