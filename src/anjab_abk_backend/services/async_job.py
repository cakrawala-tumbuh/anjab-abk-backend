"""SEAM job asinkron: kontrak `AsyncJobService`."""

from __future__ import annotations

from typing import Protocol

from ..schemas.async_job import AsyncJobRead, StatusJob
from ..schemas.common import FiturKode


class AsyncJobService(Protocol):
    """Kontrak penyimpanan & mesin status job asinkron (tanpa produsen job)."""

    def create(
        self, fitur: FiturKode, jenis: str, ref_id: str | None, dibuat_oleh: str | None
    ) -> AsyncJobRead:
        """Buat job berstatus `PENDING`.

        Raises:
            FiturNonaktifError: flag `fitur` mati (409 `feature_disabled`).
        """
        ...

    def transisi(self, job_id: str, ke: StatusJob, error_code: str | None = None) -> AsyncJobRead:
        """Pindahkan job ke status `ke` sesuai `TRANSISI_SAH`.

        Raises:
            NotFoundError: job tak ada (404).
            ConflictError: transisi tak sah (409).
        """
        ...

    def get(self, job_id: str) -> AsyncJobRead:
        """Baca job; `NotFoundError` bila tak ada."""
        ...
