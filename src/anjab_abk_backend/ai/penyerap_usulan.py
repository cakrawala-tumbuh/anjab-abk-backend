"""Penyerap hasil run AI non-narasi ke tabel `ai_usulan`.

Berbeda dari `narasi/penyerap.py`, modul ini hanya menulis `ai_usulan`: tidak pernah
`narasi_versi`, `narasi_versi_sumber`, `narasi_event`, maupun `narasi_ai_permintaan`, dan tidak
memanggil `catat_event`. Dipanggil dari loop penyerap yang sudah ada (tanpa entrypoint baru).
Keluaran model (`isi`, `amplop`) tidak pernah dicatat ke log.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import AiRunModel, AiUsulanModel, _utcnow
from ..schemas.ai_run import StatusQaAi
from ..schemas.ai_usulan import HasilSerapUsulan
from ..services.ai_run import hash_masukan
from ..services.ai_run_sql import SqlAiRunService
from .fungsi_p01 import aturan_p01
from .fungsi_p02 import aturan_p02
from .fungsi_p04 import aturan_p04

__all__ = ["ATURAN_ISI", "serap_usulan", "serap_usulan_tertunda"]

logger = logging.getLogger("anjab_abk_backend.ai.penyerap_usulan")

FabrikSesi = Callable[[], AbstractContextManager[Session]]
"""Pembuat unit-of-work: konteks yang mengembalikan sesi dan commit saat keluar."""

BATCH_BAWAAN = 20
"""Jumlah usulan maksimum yang diproses per putaran polling."""

KODE_RUN_HILANG = "RUN_HILANG"
KODE_KELUARAN_TIDAK_SAH = "KELUARAN_TIDAK_SAH"
KODE_GALAT_SERAP = "GALAT_SERAP"

KUNCI_AMPLOP = ("source_refs", "cited_spans", "confidence_reason", "unknowns", "contradictions")
"""Kunci amplop keluaran yang disimpan di `ai_usulan.amplop`."""

ATURAN_ISI: dict[str, Callable[[dict[str, Any], dict[str, Any]], list[str]]] = {
    "P01": aturan_p01,
    "P02": aturan_p02,
    "P04": aturan_p04,
}
"""Pemeriksaan pasca-validasi `isi` per kode fungsi; mengembalikan daftar kode pelanggaran.

Signature aturan `(isi, amplop)`; `amplop` hasil `_amplop(keluaran)`. P01, P02, dan P04 punya
aturan (`FungsiAi` tidak punya kolom validator); fungsi lain tanpa entri berarti tanpa pemeriksaan
tambahan. Daftar tak kosong membuat usulan `MANUAL` tanpa `isi`.
"""


def _amplop(keluaran: dict[str, Any]) -> dict[str, Any]:
    """Ambil kunci amplop yang ada pada ``keluaran``."""
    return {k: keluaran[k] for k in KUNCI_AMPLOP if k in keluaran}


def _manual(rec: AiUsulanModel, kode: list[str]) -> HasilSerapUsulan:
    """Tandai usulan `MANUAL` tanpa `isi`/`amplop`/`output_hash`."""
    return _tandai(rec, HasilSerapUsulan.MANUAL, kode)


def _tandai(
    rec: AiUsulanModel, hasil: HasilSerapUsulan, kode: list[str] | None
) -> HasilSerapUsulan:
    """Isi `diserap_at`, `hasil_serap`, dan `kode_serap` pada usulan terklaim."""
    rec.diserap_at = _utcnow()
    rec.hasil_serap = hasil.value
    rec.kode_serap = kode
    return hasil


def _terapkan(session: Session, rec: AiUsulanModel, run: AiRunModel) -> HasilSerapUsulan:
    """Petakan run final ke kolom hasil usulan (tanpa menyentuh tabel lain)."""
    status = run.status_qa
    if status not in (StatusQaAi.LOLOS.value, StatusQaAi.EVIDENCE_GAP.value):
        return _manual(rec, list(run.kode_qa) or [status])
    keluaran = SqlAiRunService(session, get_settings()).keluaran_internal(run.id)
    if status == StatusQaAi.EVIDENCE_GAP.value:
        if keluaran is not None:
            rec.amplop = _amplop(keluaran)
        return _tandai(rec, HasilSerapUsulan.EVIDENCE_GAP, None)
    isi = (keluaran or {}).get("isi")
    if keluaran is None or not isinstance(isi, dict):
        return _manual(rec, [KODE_KELUARAN_TIDAK_SAH])
    aturan = ATURAN_ISI.get(rec.fungsi)
    amplop = _amplop(keluaran)
    pelanggaran = aturan(isi, amplop) if aturan is not None else []
    if pelanggaran:
        return _manual(rec, list(pelanggaran))
    rec.isi = isi
    rec.amplop = amplop
    rec.output_hash = hash_masukan(keluaran)
    return _tandai(rec, HasilSerapUsulan.USULAN_DIBUAT, None)


def serap_usulan(session: Session, usulan_id: str) -> HasilSerapUsulan | None:
    """Serap hasil satu run ke baris `ai_usulan` dalam transaksi sesi ``session``.

    Klaim memakai ``FOR UPDATE SKIP LOCKED`` pada baris yang ``diserap_at``-nya masih null,
    sehingga idempoten: usulan yang sudah diserap, dikunci penyerap lain, atau run-nya masih
    ``MENUNGGU`` tidak diubah. Semua hasil akhir, termasuk ``MANUAL``, mengisi ``diserap_at``.
    Galat tak terduga saat memetakan (tafsir konservatif) menjadi ``MANUAL`` berkode
    ``GALAT_SERAP`` agar usulan itu tidak terklaim berulang.

    Args:
        session: Sesi basis data; pemanggil yang commit.
        usulan_id: Id baris ``ai_usulan``.

    Returns:
        ``HasilSerapUsulan`` yang ditulis, atau ``None`` bila tidak ada efek.
    """
    rec = session.scalars(
        select(AiUsulanModel)
        .where(AiUsulanModel.id == usulan_id, AiUsulanModel.diserap_at.is_(None))
        .with_for_update(skip_locked=True)
    ).one_or_none()
    if rec is None:
        return None
    run = session.get(AiRunModel, rec.ai_run_id)
    if run is None:
        return _manual(rec, [KODE_RUN_HILANG])
    if run.status_qa == StatusQaAi.MENUNGGU.value:
        return None
    try:
        return _terapkan(session, rec, run)
    except Exception as exc:
        logger.error("ai_usulan_serap_galat", extra={"jenis": type(exc).__name__})
        rec.isi = rec.amplop = rec.output_hash = None
        return _manual(rec, [KODE_GALAT_SERAP])


def serap_usulan_tertunda(fabrik_sesi: FabrikSesi, limit: int = BATCH_BAWAAN) -> int:
    """Serap hingga ``limit`` usulan yang run-nya sudah final, satu transaksi per usulan.

    Galat tak terduga pada satu usulan dicatat (hanya nama jenisnya) dan putaran berlanjut.

    Args:
        fabrik_sesi: Pembuat unit-of-work sesi.
        limit: Batas jumlah usulan per panggilan.

    Returns:
        Jumlah usulan yang diberi hasil serap.
    """
    with fabrik_sesi() as s:
        ids = list(
            s.scalars(
                select(AiUsulanModel.id)
                .join(AiRunModel, AiRunModel.id == AiUsulanModel.ai_run_id)
                .where(
                    AiUsulanModel.diserap_at.is_(None),
                    AiRunModel.status_qa != StatusQaAi.MENUNGGU.value,
                )
                .order_by(AiUsulanModel.created_at, AiUsulanModel.id)
                .limit(limit)
            ).all()
        )
    diserap = 0
    for uid in ids:
        try:
            with fabrik_sesi() as s:
                if serap_usulan(s, uid) is not None:
                    diserap += 1
        except Exception as exc:
            logger.error("ai_usulan_penyerap_gagal", extra={"jenis": type(exc).__name__})
    return diserap
