"""SEAM pembanding skema basis data: kontrak `SkemaDbService`."""

from __future__ import annotations

from typing import Protocol

from ..schemas.skema_db import SkemaDbRead


class SkemaDbService(Protocol):
    """Kontrak pembacaan revisi skema aktif dan selisihnya terhadap model ORM (hanya baca)."""

    def baca(self) -> SkemaDbRead:
        """Bandingkan basis data aktif dengan head migrasi kode dan model ORM.

        Returns:
            SkemaDbRead: revisi aktif, head kode, status keselarasan, dan selisih model.

        Raises:
            ServiceUnavailableError: basis data tak terjangkau (503).
        """
        ...
