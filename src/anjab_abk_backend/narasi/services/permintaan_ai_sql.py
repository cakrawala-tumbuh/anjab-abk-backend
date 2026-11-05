"""Implementasi `PermintaanAiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import AsyncJobModel, NarasiAiPermintaanModel
from ...schemas.async_job import StatusJob
from ..schemas.permintaan_ai import PermintaanAiRead


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None or dt.tzinfo is not None:
        return dt
    return dt.replace(tzinfo=UTC)


def _to_read(rec: NarasiAiPermintaanModel, job: AsyncJobModel | None) -> PermintaanAiRead:
    """Proyeksikan baris permintaan dan job-nya; job hilang dibaca `FAILED`."""
    return PermintaanAiRead(
        id=rec.id,
        job_id=rec.job_id,
        job_status=StatusJob(job.status) if job is not None else StatusJob.FAILED,
        job_error_code=job.error_code if job is not None else "JOB_HILANG",
        ai_run_id=rec.ai_run_id,
        sumber_ids=list(rec.sumber_ids),
        created_at=_aware(rec.created_at),  # type: ignore[arg-type]
        diserap_at=_aware(rec.diserap_at),
        hasil_serap=rec.hasil_serap,
        kode_serap=list(rec.kode_serap) if rec.kode_serap is not None else None,
    )


class SqlPermintaanAiService:
    """`PermintaanAiService` berbasis PostgreSQL; terikat satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def catat(
        self,
        narasi_id: str,
        job_id: str,
        ai_run_id: str,
        sumber_ids: list[str],
        diminta_oleh: str,
    ) -> PermintaanAiRead:
        """Simpan permintaan baru lalu `flush`.

        Args:
            narasi_id: Id kasus.
            job_id: Id `async_job` hasil pengajuan.
            ai_run_id: Id `ai_run` (dari `AsyncJobRead.ref_id`).
            sumber_ids: Sumber yang diajukan.
            diminta_oleh: Subjek pemohon.

        Returns:
            Proyeksi permintaan dengan status job terkini.
        """
        rec = NarasiAiPermintaanModel(
            id=str(uuid.uuid4()),
            narasi_id=narasi_id,
            job_id=job_id,
            ai_run_id=ai_run_id,
            sumber_ids=list(sumber_ids),
            diminta_oleh=diminta_oleh,
        )
        self._s.add(rec)
        self._s.flush()
        self._s.refresh(rec)
        return _to_read(rec, self._s.get(AsyncJobModel, job_id))

    def ada_belum_diserap(self, narasi_id: str) -> bool:
        """True bila ada permintaan kasus dengan `diserap_at` null."""
        stmt = (
            select(NarasiAiPermintaanModel.id)
            .where(
                NarasiAiPermintaanModel.narasi_id == narasi_id,
                NarasiAiPermintaanModel.diserap_at.is_(None),
            )
            .limit(1)
        )
        return self._s.execute(stmt).first() is not None

    def list_by_narasi(
        self, narasi_id: str, *, limit: int, offset: int
    ) -> tuple[list[PermintaanAiRead], int]:
        """Daftar permintaan kasus, terbaru dulu, dengan status job lewat LEFT JOIN."""
        m = NarasiAiPermintaanModel
        total = self._s.execute(
            select(func.count()).select_from(m).where(m.narasi_id == narasi_id)
        ).scalar_one()
        rows = self._s.execute(
            select(m, AsyncJobModel)
            .outerjoin(AsyncJobModel, AsyncJobModel.id == m.job_id)
            .where(m.narasi_id == narasi_id)
            .order_by(m.created_at.desc(), m.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [_to_read(rec, job) for rec, job in rows], int(total)
