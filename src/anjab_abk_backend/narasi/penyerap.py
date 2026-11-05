"""Penyerap hasil run AI ke versi narasi (proses terpisah dari worker job AI).

Worker (`ai/worker.py`) hanya menulis `ai_run` dan `async_job`. Modul ini memindahkan hasil
run yang sudah final ke `narasi_versi` lewat `NarasiService.tambah_versi`, satu transaksi per
permintaan (`narasi_ai_permintaan`). Penyerap tidak pernah memanggil `catat_event`: ia tidak
dapat menyetujui, menolak, atau meninjau apa pun.

Jalankan dengan ``python -m anjab_abk_backend.narasi.penyerap``. Bila flag
``FEATURE_AI_NARRATIVE_DRAFT`` mati, proses mencatat log lalu keluar kode 0; selain itu ia
polling tiap ``AI_WORKER_POLL_DETIK`` dan berhenti rapi pada SIGTERM. Tiap putaran juga
menyerap usulan fungsi AI non-narasi lewat ``ai.penyerap_usulan.serap_usulan_tertunda``
(hanya menulis ``ai_usulan``).

Setiap hasil akhir menandai ``diserap_at`` supaya permintaan itu tidak lagi menahan kasus
(`PermintaanAiService.ada_belum_diserap`). Hanya run ``MENUNGGU`` yang dibiarkan.
"""

from __future__ import annotations

import logging
import signal
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from enum import StrEnum
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..ai.penyerap_usulan import serap_usulan_tertunda
from ..config import get_settings
from ..errors import AppError, ValidationAppError
from ..fitur import fitur_aktif
from ..models import (
    AiRunModel,
    NarasiAiPermintaanModel,
    NarasiKasusModel,
    NarasiVersiModel,
    _utcnow,
)
from ..schemas.ai_run import StatusQaAi
from ..services.ai_run import hash_masukan
from ..services.ai_run_sql import SqlAiRunService
from .schemas.kasus import METADATA_AI_KUNCI, BasisRelation, RevisionOrigin, StatusNarasi
from .schemas.mesin import AKTOR_AI_WORKER, AktorNarasi, KutipanSumber
from .services.narasi import TransisiTidakSahError, VersiBasiError
from .services.narasi_sql import SqlNarasiService

__all__ = ["HasilSerap", "main", "serap_run", "serap_tertunda"]

logger = logging.getLogger("anjab_abk_backend.narasi.penyerap")

FabrikSesi = Callable[[], AbstractContextManager[Session]]
"""Pembuat unit-of-work: konteks yang mengembalikan sesi dan commit saat keluar."""

AKTOR_PENYERAP = AktorNarasi(key=AKTOR_AI_WORKER, role="SYSTEM")
"""Aktor penulisan versi oleh penyerap (tanpa token)."""

STATUS_KASUS_BOLEH_SERAP = frozenset({StatusNarasi.SOURCE_CHECKED, StatusNarasi.NEED_FACT})
"""Status kasus saat hasil run boleh dijadikan versi (sama dengan syarat pengajuan)."""

BATCH_BAWAAN = 20
"""Jumlah permintaan maksimum yang diproses per putaran polling."""

KODE_ATURAN_SND_DILANGGAR = "ATURAN_SND_DILANGGAR"
KODE_KASUS_BERUBAH = "KASUS_BERUBAH"
KODE_VERSI_DITOLAK = "VERSI_DITOLAK"
KODE_GALAT_SERAP = "GALAT_SERAP"


class HasilSerap(StrEnum):
    """Nilai `narasi_ai_permintaan.hasil_serap`."""

    VERSI_DIBUAT = "VERSI_DIBUAT"
    NEED_FACT = "NEED_FACT"
    MANUAL = "MANUAL"


class _Pelanggaran(Exception):
    """Hasil run melanggar aturan serap; membawa kode `kode_serap`."""

    def __init__(self, kode: str) -> None:
        super().__init__(kode)
        self.kode = kode


def _metadata_ai(keluaran: dict[str, Any]) -> dict[str, Any]:
    """Susun `metadata_ai` dari amplop dan `isi`; hanya kunci di `METADATA_AI_KUNCI`."""
    sumber = {**keluaran, **(keluaran.get("isi") or {})}
    return {k: sumber[k] for k in METADATA_AI_KUNCI if k in sumber}


def _kutipan(run: AiRunModel, keluaran: dict[str, Any]) -> list[KutipanSumber]:
    """Satu kutipan `DIRECT` per `cited_spans`; hash dari `source_refs`, lalu `ai_run.sumber`."""
    hash_sumber = {x["source_id"]: x["source_hash"] for x in run.sumber}
    hash_sumber.update({x["source_id"]: x["source_hash"] for x in keluaran["source_refs"]})
    hasil = []
    for kutip in keluaran["cited_spans"]:
        sid = kutip["source_id"]
        if sid not in hash_sumber:
            raise _Pelanggaran(KODE_VERSI_DITOLAK)
        hasil.append(
            KutipanSumber(
                sumber_id=sid,
                source_hash=hash_sumber[sid],
                basis_relation=BasisRelation.DIRECT,
                source_span=kutip["span"],
            )
        )
    return hasil


def _putuskan(
    run: AiRunModel, keluaran: dict[str, Any] | None
) -> tuple[StatusNarasi, str | None, list[KutipanSumber], str | None, dict[str, Any] | None]:
    """Petakan run final ke ``(status_hasil, teks, sumber, output_hash, metadata_ai)``.

    Raises:
        _Pelanggaran: `ATURAN_SND_DILANGGAR` bila `draft_text` tidak sesuai status run.
    """
    if run.status_qa == StatusQaAi.LOLOS.value:
        draf = (keluaran or {}).get("isi", {}).get("draft_text")
        if keluaran is None or not isinstance(draf, str) or not draf.strip():
            raise _Pelanggaran(KODE_ATURAN_SND_DILANGGAR)
        return (
            StatusNarasi.AI_DRAFT,
            draf,
            _kutipan(run, keluaran),
            hash_masukan(keluaran),
            _metadata_ai(keluaran),
        )
    # EVIDENCE_GAP
    if keluaran is None:
        fakta = list(run.kode_qa) or ["SUMBER_KOSONG"]
        return StatusNarasi.NEED_FACT, None, [], None, {"missing_facts": fakta}
    if keluaran.get("isi", {}).get("draft_text") is not None:
        raise _Pelanggaran(KODE_ATURAN_SND_DILANGGAR)
    return (
        StatusNarasi.NEED_FACT,
        None,
        _kutipan(run, keluaran),
        hash_masukan(keluaran),
        _metadata_ai(keluaran),
    )


def _tandai(rec: NarasiAiPermintaanModel, hasil: HasilSerap, kode: list[str] | None) -> HasilSerap:
    """Isi `diserap_at`, `hasil_serap`, dan `kode_serap` pada permintaan terklaim."""
    rec.diserap_at = _utcnow()
    rec.hasil_serap = hasil.value
    rec.kode_serap = kode
    return hasil


def serap_run(session: Session, permintaan_id: str) -> HasilSerap | None:
    """Serap hasil satu run ke versi narasi dalam transaksi sesi ``session``.

    Klaim memakai ``FOR UPDATE SKIP LOCKED`` pada baris permintaan yang ``diserap_at``-nya
    masih null. Idempoten: permintaan yang sudah diserap, sedang dikunci penyerap lain, atau
    run-nya masih ``MENUNGGU`` tidak diubah sama sekali. Pagar kedua: ``narasi_versi.ai_run_id``
    UNIQUE; bila versi untuk run itu sudah ada, tidak dibuat versi kedua.

    Semua hasil akhir mengisi ``diserap_at``. Pemetaan galat ``tambah_versi`` (tafsir
    konservatif, tanpa versi, kasus tetap): ``TransisiTidakSahError``/``VersiBasiError`` dan
    status kasus di luar ``STATUS_KASUS_BOLEH_SERAP`` menjadi ``KASUS_BERUBAH``;
    ``ValidationAppError`` (sumber/hash/``NO_SOURCE_NO_FACT``) menjadi ``VERSI_DITOLAK``;
    ``AppError`` atau ``IntegrityError`` lain menjadi ``GALAT_SERAP``.

    Args:
        session: Sesi basis data; pemanggil yang commit.
        permintaan_id: Id baris ``narasi_ai_permintaan``.

    Returns:
        ``HasilSerap`` yang ditulis, atau ``None`` bila tidak ada efek.
    """
    rec = session.scalars(
        select(NarasiAiPermintaanModel)
        .where(
            NarasiAiPermintaanModel.id == permintaan_id,
            NarasiAiPermintaanModel.diserap_at.is_(None),
        )
        .with_for_update(skip_locked=True)
    ).one_or_none()
    if rec is None:
        return None
    run = session.get(AiRunModel, rec.ai_run_id)
    if run is None:
        return _tandai(rec, HasilSerap.MANUAL, ["RUN_HILANG"])
    if run.status_qa == StatusQaAi.MENUNGGU.value:
        return None
    if run.status_qa not in (StatusQaAi.LOLOS.value, StatusQaAi.EVIDENCE_GAP.value):
        return _tandai(rec, HasilSerap.MANUAL, list(run.kode_qa) or [run.status_qa])

    sudah = session.scalar(select(NarasiVersiModel.id).where(NarasiVersiModel.ai_run_id == run.id))
    if sudah is not None:
        return _tandai(rec, HasilSerap.VERSI_DIBUAT, None)

    narasi = SqlNarasiService(session)
    try:
        kasus = session.scalars(
            select(NarasiKasusModel).where(NarasiKasusModel.id == rec.narasi_id).with_for_update()
        ).one_or_none()
        if kasus is None or StatusNarasi(kasus.status) not in STATUS_KASUS_BOLEH_SERAP:
            raise _Pelanggaran(KODE_KASUS_BERUBAH)
        keluaran = SqlAiRunService(session, get_settings()).keluaran_internal(run.id)
        status, teks, sumber, output_hash, metadata = _putuskan(run, keluaran)
        terbaru = narasi.versi_terbaru(rec.narasi_id)
        with session.begin_nested():
            narasi.tambah_versi(
                rec.narasi_id,
                revision_origin=RevisionOrigin.AI_DRAFT,
                status_hasil=status,
                teks=teks,
                sumber=sumber,
                supersedes_id=terbaru.id if terbaru else None,
                aktor=AKTOR_PENYERAP,
                ai_run_id=run.id,
                output_hash=output_hash,
                metadata_ai=metadata,
            )
    except _Pelanggaran as exc:
        return _tandai(rec, HasilSerap.MANUAL, [exc.kode])
    except (TransisiTidakSahError, VersiBasiError):
        return _tandai(rec, HasilSerap.MANUAL, [KODE_KASUS_BERUBAH])
    except ValidationAppError:
        return _tandai(rec, HasilSerap.MANUAL, [KODE_VERSI_DITOLAK])
    except (AppError, IntegrityError, KeyError, TypeError, ValueError):
        return _tandai(rec, HasilSerap.MANUAL, [KODE_GALAT_SERAP])
    hasil = HasilSerap.VERSI_DIBUAT if status is StatusNarasi.AI_DRAFT else HasilSerap.NEED_FACT
    return _tandai(rec, hasil, None)


def serap_tertunda(fabrik_sesi: FabrikSesi, limit: int = BATCH_BAWAAN) -> int:
    """Serap hingga ``limit`` permintaan yang run-nya sudah final, satu transaksi per permintaan.

    Galat tak terduga pada satu permintaan dicatat (hanya nama jenisnya, tanpa isi) dan
    putaran berlanjut ke permintaan berikutnya, sehingga satu permintaan bermasalah tidak
    menghentikan yang lain.

    Args:
        fabrik_sesi: Pembuat unit-of-work sesi.
        limit: Batas jumlah permintaan per panggilan.

    Returns:
        Jumlah permintaan yang diberi hasil serap.
    """
    with fabrik_sesi() as s:
        ids = list(
            s.scalars(
                select(NarasiAiPermintaanModel.id)
                .join(AiRunModel, AiRunModel.id == NarasiAiPermintaanModel.ai_run_id)
                .where(
                    NarasiAiPermintaanModel.diserap_at.is_(None),
                    AiRunModel.status_qa != StatusQaAi.MENUNGGU.value,
                )
                .order_by(NarasiAiPermintaanModel.created_at, NarasiAiPermintaanModel.id)
                .limit(limit)
            ).all()
        )
    diserap = 0
    for pid in ids:
        try:
            with fabrik_sesi() as s:
                if serap_run(s, pid) is not None:
                    diserap += 1
        except Exception as exc:
            logger.error("narasi_penyerap_gagal", extra={"jenis": type(exc).__name__})
    return diserap


def main() -> int:
    """Titik masuk proses penyerap.

    Returns:
        Kode keluar proses (0 bila flag mati atau dihentikan dengan SIGTERM).
    """
    from ..ai.gateway import FITUR_AI
    from ..db import session_scope

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    if not fitur_aktif(FITUR_AI, settings):
        logger.info("narasi_penyerap_keluar_flag_mati")
        return 0
    berhenti = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: berhenti.set())
    signal.signal(signal.SIGINT, lambda *_: berhenti.set())
    while not berhenti.is_set():
        n = 0
        try:
            n += serap_tertunda(session_scope)
        except Exception as exc:
            logger.error("narasi_penyerap_putaran_gagal", extra={"jenis": type(exc).__name__})
        try:
            n += serap_usulan_tertunda(session_scope)
        except Exception as exc:
            logger.error("ai_usulan_penyerap_putaran_gagal", extra={"jenis": type(exc).__name__})
        if n == 0:
            berhenti.wait(settings.ai_worker_poll_detik)
    logger.info("narasi_penyerap_berhenti")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
