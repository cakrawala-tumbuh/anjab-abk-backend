"""SEAM penyimpanan permintaan draf AI atas kasus narasi."""

from __future__ import annotations

from typing import Protocol

from ..schemas.permintaan_ai import PermintaanAiRead


class PermintaanAiService(Protocol):
    """Kontrak tabel `narasi_ai_permintaan`: tautan kasus, job, dan `ai_run`."""

    def catat(
        self,
        narasi_id: str,
        job_id: str,
        ai_run_id: str,
        sumber_ids: list[str],
        diminta_oleh: str,
    ) -> PermintaanAiRead:
        """Simpan satu permintaan baru dan kembalikan proyeksinya dengan status job."""
        ...

    def ada_belum_diserap(self, narasi_id: str) -> bool:
        """True bila kasus punya permintaan yang `diserap_at`-nya masih null."""
        ...

    def list_by_narasi(
        self, narasi_id: str, *, limit: int, offset: int
    ) -> tuple[list[PermintaanAiRead], int]:
        """Daftar permintaan kasus, terbaru dulu, beserta total."""
        ...
