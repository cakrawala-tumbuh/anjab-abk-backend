"""Implementasi PostgreSQL `AsyncJobService`."""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import ConflictError, NotFoundError
from ..fitur import FiturNonaktifError, fitur_aktif
from ..models import AsyncJobModel
from ..schemas.async_job import TRANSISI_SAH, AsyncJobRead, StatusJob
from ..schemas.common import FiturKode


class SqlAsyncJobService:
    """`AsyncJobService` di atas satu `Session` per request."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._s = session
        self._settings = settings

    def create(
        self, fitur: FiturKode, jenis: str, ref_id: str | None, dibuat_oleh: str | None
    ) -> AsyncJobRead:
        """Buat job `PENDING` bila flag `fitur` hidup; tolak tanpa menyimpan bila mati."""
        if not fitur_aktif(fitur, self._settings):
            raise FiturNonaktifError(fitur)
        rec = AsyncJobModel(
            id=str(uuid.uuid4()),
            fitur=fitur.value,
            jenis=jenis,
            status=StatusJob.PENDING.value,
            ref_id=ref_id,
            percobaan=0,
            dibuat_oleh=dibuat_oleh,
        )
        self._s.add(rec)
        self._s.flush()
        return AsyncJobRead.model_validate(rec)

    def transisi(self, job_id: str, ke: StatusJob, error_code: str | None = None) -> AsyncJobRead:
        """Terapkan transisi sah; `FAILED -> PENDING` menaikkan `percobaan`."""
        rec = self._s.get(AsyncJobModel, job_id)
        if rec is None:
            raise NotFoundError(f"Job '{job_id}' tidak ditemukan.")
        asal = StatusJob(rec.status)
        if ke not in TRANSISI_SAH[asal]:
            raise ConflictError(f"Transisi job {asal.value} -> {ke.value} tidak diizinkan.")
        if asal is StatusJob.FAILED and ke is StatusJob.PENDING:
            rec.percobaan += 1
        rec.status = ke.value
        rec.error_code = error_code if ke in (StatusJob.FAILED, StatusJob.MANUAL_REVIEW) else None
        self._s.flush()
        return AsyncJobRead.model_validate(rec)

    def get(self, job_id: str) -> AsyncJobRead:
        """Baca job atau `NotFoundError`."""
        rec = self._s.get(AsyncJobModel, job_id)
        if rec is None:
            raise NotFoundError(f"Job '{job_id}' tidak ditemukan.")
        return AsyncJobRead.model_validate(rec)
