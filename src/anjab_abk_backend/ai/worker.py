"""Worker job AI: mengklaim satu job, memanggil model, memeriksa, lalu menutup run.

Jalankan dengan ``python -m anjab_abk_backend.ai.worker``. Bila flag
``FEATURE_AI_NARRATIVE_DRAFT`` mati, proses mencatat log lalu keluar kode 0.
Selain itu worker polling tiap ``AI_WORKER_POLL_DETIK``, memproses satu job
sekali jalan, dan keluar rapi saat menerima SIGTERM (job berjalan diselesaikan).

Klaim memakai ``FOR UPDATE SKIP LOCKED`` dan di-commit sebagai ``RUNNING``
SEBELUM model dipanggil; tidak ada transaksi terbuka selama panggilan model.
Satu-satunya tabel yang ditulis adalah ``ai_run`` dan ``async_job``.
"""

from __future__ import annotations

import json
import logging
import signal
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..fitur import ai_boleh_jalan, fitur_aktif
from ..models import AiRunModel, AsyncJobModel, _utcnow
from ..schemas.ai_run import StatusQaAi
from ..schemas.async_job import AsyncJobRead, StatusJob
from ..services.ai_run_sql import SqlAiRunService
from ..services.async_job_sql import SqlAsyncJobService
from .gateway import FITUR_AI, FUNGSI_TERDAFTAR, FungsiAi
from .guardrail import susun_instruksi
from .keluaran import cek_keluaran, skema_dengan_amplop
from .klien import (
    AnthropicKlienModel,
    JawabanModel,
    KesalahanModelPermanen,
    KesalahanModelSementara,
    KlienModel,
    KunciModelTidakAda,
)
from .redaksi import muat_kamus_nama, periksa_pii

__all__ = ["jalankan_satu", "klaim_job", "main", "pulihkan_job_basi"]

logger = logging.getLogger("anjab_abk_backend.ai.worker")

FabrikSesi = Callable[[], AbstractContextManager[Session]]
"""Pembuat unit-of-work: konteks yang mengembalikan sesi dan commit saat keluar."""


def pulihkan_job_basi(session: Session, settings: Settings) -> int:
    """Tandai job ``RUNNING`` yang terlalu lama sebagai ``FAILED`` ``WORKER_TERHENTI``.

    Batas basi adalah ``AI_TIMEOUT_DETIK`` x 2 sejak ``updated_at``. Job basi
    tidak diulang otomatis.

    Args:
        session: Sesi basis data.
        settings: Pengaturan aplikasi.

    Returns:
        Jumlah job yang dipulihkan.
    """
    batas = _utcnow() - timedelta(seconds=settings.ai_timeout_detik * 2)
    ids = session.scalars(
        select(AsyncJobModel.id)
        .where(
            AsyncJobModel.fitur == FITUR_AI.value,
            AsyncJobModel.status == StatusJob.RUNNING.value,
            AsyncJobModel.updated_at < batas,
        )
        .with_for_update(skip_locked=True)
    ).all()
    jobs = SqlAsyncJobService(session, settings)
    for job_id in ids:
        jobs.transisi(job_id, StatusJob.FAILED, "WORKER_TERHENTI")
    return len(ids)


def klaim_job(session: Session, settings: Settings) -> AsyncJobRead | None:
    """Klaim job ``PENDING`` tertua dan pindahkan ke ``RUNNING``.

    Memakai ``FOR UPDATE SKIP LOCKED`` sehingga dua pengklaim bersamaan tidak
    mengambil job yang sama. Pemanggil wajib commit sebelum memanggil model.

    Args:
        session: Sesi basis data.
        settings: Pengaturan aplikasi.

    Returns:
        Job yang diklaim, atau ``None`` bila tidak ada.
    """
    job_id = session.scalars(
        select(AsyncJobModel.id)
        .where(
            AsyncJobModel.fitur == FITUR_AI.value,
            AsyncJobModel.status == StatusJob.PENDING.value,
        )
        .order_by(AsyncJobModel.created_at, AsyncJobModel.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job_id is None:
        return None
    return SqlAsyncJobService(session, settings).transisi(job_id, StatusJob.RUNNING)


def _selesaikan_manual(
    session: Session,
    settings: Settings,
    job_id: str,
    run_id: str | None,
    status: StatusQaAi,
    kode: list[str],
    keluaran: dict[str, Any] | None = None,
    jawaban: JawabanModel | None = None,
    error_code: str | None = None,
) -> None:
    """Tutup run (bila ada) dan pindahkan job ke ``MANUAL_REVIEW``."""
    if run_id is not None:
        SqlAiRunService(session, settings).tutup(
            run_id,
            status,
            kode,
            keluaran,
            jawaban.stop_reason if jawaban else None,
            jawaban.model_dilayani if jawaban else None,
            jawaban.input_tokens if jawaban else None,
            jawaban.output_tokens if jawaban else None,
        )
    SqlAsyncJobService(session, settings).transisi(
        job_id, StatusJob.MANUAL_REVIEW, error_code or (kode[0] if kode else None)
    )


def _evaluasi(
    jawaban: JawabanModel, fungsi: FungsiAi, sumber: dict[str, tuple[str, str]], kamus: list[str]
) -> tuple[StatusQaAi, list[str], dict[str, Any] | None]:
    """Putuskan status run dari jawaban model (tanpa efek samping)."""
    if jawaban.stop_reason == "refusal":
        return StatusQaAi.KARANTINA, ["MODEL_MENOLAK"], None
    if jawaban.stop_reason == "max_tokens":
        return StatusQaAi.KARANTINA, ["KELUARAN_TERPOTONG"], None
    hasil = cek_keluaran(jawaban.teks or "", skema_dengan_amplop(fungsi.skema_isi), sumber)
    if hasil.status_qa == "KARANTINA" or hasil.keluaran is None:
        return StatusQaAi.KARANTINA, list(hasil.kode), None
    teks_keluaran = json.dumps(hasil.keluaran, ensure_ascii=False)
    if periksa_pii(teks_keluaran, kamus).temuan:
        return StatusQaAi.KARANTINA, ["PII_KELUARAN"], None
    return StatusQaAi(hasil.status_qa), [], hasil.keluaran


def jalankan_satu(
    fabrik_sesi: FabrikSesi,
    settings: Settings,
    buat_klien: Callable[[], KlienModel] | None = None,
    registri: dict[str, FungsiAi] | None = None,
) -> str | None:
    """Klaim dan proses satu job AI.

    Tahap 1 (satu transaksi, di-commit sebelum model dipanggil): periksa
    saklar, klaim job, baca run. Tahap 2 (tanpa transaksi): panggil model.
    Tahap 3 (satu transaksi): periksa saklar lagi, validasi keluaran, tutup run
    dan pindahkan job.

    Args:
        fabrik_sesi: Pembuat unit-of-work sesi.
        settings: Pengaturan aplikasi.
        buat_klien: Pembuat ``KlienModel``; dipanggil hanya bila model akan
            dipanggil. Bawaan ``AnthropicKlienModel``.
        registri: Registri fungsi; bawaan ``FUNGSI_TERDAFTAR``.

    Returns:
        Id job yang diproses, atau ``None`` bila saklar mati atau tidak ada job.
    """
    reg = FUNGSI_TERDAFTAR if registri is None else registri
    with fabrik_sesi() as s:
        if not ai_boleh_jalan(s, settings, FITUR_AI):
            return None
        job = klaim_job(s, settings)
        if job is None:
            return None
        run = s.get(AiRunModel, job.ref_id) if job.ref_id else None
        fungsi = reg.get(run.fungsi) if run is not None else None
        masukan = dict(run.masukan) if run is not None and run.masukan else None
        kamus = muat_kamus_nama(s)
        if run is None or fungsi is None or masukan is None:
            kode = "RUN_HILANG" if run is None else "FUNGSI_ATAU_MASUKAN_HILANG"
            _selesaikan_manual(
                s, settings, job.id, run.id if run else None, StatusQaAi.GAGAL, [kode]
            )
            return job.id
        run_id = run.id

    sumber_peta = {x["source_id"]: (x["source_hash"], x["teks"]) for x in masukan["sumber"]}
    masukan_json = json.dumps(
        {"sumber": masukan["sumber"], "parameter": masukan["parameter"]},
        ensure_ascii=False,
        sort_keys=True,
    )
    skema = skema_dengan_amplop(fungsi.skema_isi)
    jawaban: JawabanModel | None = None
    galat: str | None = None
    sementara = False
    try:
        klien = (buat_klien or (lambda: AnthropicKlienModel(settings)))()
        jawaban = klien.panggil(susun_instruksi(fungsi.instruksi), masukan_json, skema)
    except KesalahanModelSementara:
        galat, sementara = "MODEL_SEMENTARA", True
    except KesalahanModelPermanen:
        galat = "MODEL_PERMANEN"
    except KunciModelTidakAda:
        galat = "KUNCI_MODEL_TIDAK_ADA"
    except Exception as exc:
        logger.error("ai_worker_galat_tak_terduga", extra={"jenis": type(exc).__name__})
        galat = "GALAT_INTERNAL"

    with fabrik_sesi() as s:
        jobs = SqlAsyncJobService(s, settings)
        if galat is not None:
            if sementara and job.percobaan + 1 < settings.ai_job_maks_percobaan:
                jobs.transisi(job.id, StatusJob.FAILED, galat)
                jobs.transisi(job.id, StatusJob.PENDING)
            else:
                _selesaikan_manual(s, settings, job.id, run_id, StatusQaAi.GAGAL, [galat])
            return job.id
        assert jawaban is not None
        if not ai_boleh_jalan(s, settings, FITUR_AI):
            status, kode, keluaran = StatusQaAi.KARANTINA, ["SAKLAR_DIMATIKAN"], None
        else:
            status, kode, keluaran = _evaluasi(jawaban, fungsi, sumber_peta, kamus)
        if status is StatusQaAi.LOLOS:
            SqlAiRunService(s, settings).tutup(
                run_id, status, kode, keluaran, jawaban.stop_reason, jawaban.model_dilayani,
                jawaban.input_tokens, jawaban.output_tokens,
            )  # fmt: skip
            jobs.transisi(job.id, StatusJob.SUCCEEDED)
        else:
            _selesaikan_manual(s, settings, job.id, run_id, status, kode, keluaran, jawaban)
    return job.id


def main() -> int:
    """Titik masuk proses worker.

    Returns:
        Kode keluar proses (0 bila flag mati atau dihentikan dengan SIGTERM).
    """
    from ..db import session_scope

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    if not fitur_aktif(FITUR_AI, settings):
        logger.info("ai_worker_keluar_flag_mati")
        return 0
    berhenti = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: berhenti.set())
    signal.signal(signal.SIGINT, lambda *_: berhenti.set())
    try:
        with session_scope() as s:
            n = pulihkan_job_basi(s, settings)
        if n:
            logger.warning("ai_worker_job_basi_dipulihkan", extra={"jumlah": n})
    except Exception as exc:
        logger.error("ai_worker_pemulihan_gagal", extra={"jenis": type(exc).__name__})
    while not berhenti.is_set():
        try:
            diproses = jalankan_satu(session_scope, settings)
        except Exception as exc:
            logger.error("ai_worker_putaran_gagal", extra={"jenis": type(exc).__name__})
            diproses = None
        if diproses is None:
            berhenti.wait(settings.ai_worker_poll_detik)
    logger.info("ai_worker_berhenti")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
