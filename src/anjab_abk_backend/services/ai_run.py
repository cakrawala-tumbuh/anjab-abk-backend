"""SEAM register run AI: kontrak `AiRunService` dan helper hash/`Protocol_ID`."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol

from .. import __version__
from ..config import Settings
from ..schemas.ai_run import AiRunRead, AiSumber, StatusQaAi

__all__ = ["AiRunService", "bangun_protocol_id", "hash_masukan"]


def hash_masukan(obj: Any) -> str:
    """Hitung SHA-256 heksadesimal dari JSON kanonik ``obj``.

    JSON kanonik memakai ``sort_keys=True`` dan ``ensure_ascii=False`` sehingga urutan kunci
    tidak memengaruhi hasil.

    Args:
        obj: nilai yang dapat diserialisasi ke JSON.

    Returns:
        str: 64 karakter heksadesimal.
    """
    kanonik = json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(kanonik.encode("utf-8")).hexdigest()


def bangun_protocol_id(fungsi: str, prompt_version: str, settings: Settings) -> str:
    """Susun ``Protocol_ID`` ``<arm>/<versi>+<commit 12>/<fungsi>@<prompt_version>``.

    Args:
        fungsi: nama fungsi AI.
        prompt_version: versi prompt.
        settings: sumber ``ai_protocol_arm`` dan ``app_build_commit``.

    Returns:
        str: contoh ``TANPA_ARM/0.48.1+unknown/draf_narasi@v1``.
    """
    commit = settings.app_build_commit[:12]
    return f"{settings.ai_protocol_arm}/{__version__}+{commit}/{fungsi}@{prompt_version}"


class AiRunService(Protocol):
    """Kontrak register run AI (tanpa pemanggil model)."""

    def buka(
        self,
        fungsi: str,
        prompt_version: str,
        prompt_hash: str,
        model_diminta: str,
        sumber: list[AiSumber],
        masukan: dict[str, Any],
        dibuat_oleh: str | None = None,
        penyedia: str | None = None,
    ) -> AiRunRead:
        """Buat run berstatus ``MENUNGGU``; ``protocol_id`` dan ``input_snapshot_id`` diturunkan.

        ``penyedia`` adalah mode penyedia saat pengajuan (null = tidak dicatat).
        """
        ...

    def catat_penyedia(self, run_id: str, penyedia: str) -> bool:
        """Timpa ``penyedia`` run yang masih ``MENUNGGU``; run final tidak diubah.

        Returns:
            ``True`` bila ditimpa, ``False`` bila run sudah final atau tidak ada.
        """
        ...

    def tutup(
        self,
        run_id: str,
        status_qa: StatusQaAi,
        kode_qa: list[str],
        keluaran: dict[str, Any] | None,
        stop_reason: str | None,
        model_dilayani: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> AiRunRead:
        """Isi hasil run sekali saja dan kosongkan ``masukan`` kecuali ``AI_SIMPAN_MASUKAN``.

        Raises:
            NotFoundError: run tak ada (404).
            ConflictError: run sudah ditutup (409); baris tidak berubah.
            ValidationAppError: ``status_qa`` bernilai ``MENUNGGU`` (422).
        """
        ...

    def get(self, run_id: str) -> AiRunRead:
        """Baca run; ``NotFoundError`` bila tak ada."""
        ...

    def keluaran_internal(self, run_id: str) -> dict[str, Any] | None:
        """Keluaran model run untuk penyerap; internal, tanpa rute dan di luar `AiRunRead`.

        Raises:
            NotFoundError: run tak ada (404).
        """
        ...

    def list(
        self,
        fungsi: str | None,
        status_qa: StatusQaAi | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AiRunRead], int]:
        """Daftar run terbaru lebih dulu beserta total setelah filter."""
        ...
