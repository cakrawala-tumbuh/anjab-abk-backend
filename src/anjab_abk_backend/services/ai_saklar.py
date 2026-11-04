"""SEAM kill switch layanan AI: kontrak `SaklarAiService`."""

from __future__ import annotations

from typing import Protocol

from ..schemas.ai_saklar import SaklarAiRead
from ..schemas.common import FiturKode

__all__ = ["SaklarAiService"]


class SaklarAiService(Protocol):
    """Kontrak saklar darurat layanan AI (event append-only)."""

    def status(self, layanan: FiturKode) -> SaklarAiRead:
        """Hitung status dari event terakhir ``layanan`` dan flag env."""
        ...

    def matikan(self, layanan: FiturKode, alasan: str, aktor: str) -> SaklarAiRead:
        """Catat event MATIKAN.

        Raises:
            ConflictError: layanan sudah dimatikan (409); tidak ada event baru.
        """
        ...

    def hidupkan(self, layanan: FiturKode, alasan: str, aktor: str) -> SaklarAiRead:
        """Catat event HIDUPKAN; tidak menyalakan flag env.

        Raises:
            ConflictError: layanan tidak sedang dimatikan (409); tidak ada event baru.
        """
        ...
