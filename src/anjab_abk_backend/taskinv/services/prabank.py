"""SEAM akses data cerita pra-bank dan log paparan Task Inventory (backlog #131)."""

from __future__ import annotations

from typing import Protocol

from ...errors import ConflictError, ValidationAppError
from ..schemas.prabank import (
    CeritaPrabankRead,
    ExposureState,
    JenisPaparan,
    PaparanRead,
    PrabankRead,
)

KODE_CERITA_SUDAH_DIKUNCI = "CERITA_SUDAH_DIKUNCI"
KODE_CERITA_KOSONG = "CERITA_KOSONG"


class CeritaSudahDikunciError(ConflictError):
    """409 `CERITA_SUDAH_DIKUNCI`: cerita sudah beku dan tidak boleh diubah."""

    error_code = KODE_CERITA_SUDAH_DIKUNCI


class CeritaKosongError(ValidationAppError):
    """422 `CERITA_KOSONG`: cerita belum ada sehingga tidak dapat dibekukan."""

    error_code = KODE_CERITA_KOSONG


class TiPrabankService(Protocol):
    """Kontrak cerita pra-bank dan log paparan satu responden TI."""

    def simpan_cerita(self, responden_id: str, teks: str) -> CeritaPrabankRead: ...
    def bekukan(self, responden_id: str) -> CeritaPrabankRead: ...
    def catat_paparan(self, responden_id: str, jenis: JenisPaparan) -> PaparanRead: ...
    def baca(self, responden_id: str) -> PrabankRead: ...
    def status_paparan(self, responden_id: str) -> ExposureState | None: ...
    def ada_paparan(self, responden_id: str) -> bool: ...
