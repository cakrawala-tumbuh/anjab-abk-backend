"""SEAM pengajuan fungsi AI non-narasi atas satu sasaran, dengan hasil disimpan sebagai usulan."""

from __future__ import annotations

from typing import Any, Protocol

from ..ai.redaksi import SumberAi
from ..errors import ConflictError
from ..schemas.ai_usulan import (
    AiUsulanPutusanCreate,
    AiUsulanPutusanRead,
    AiUsulanRead,
    AiUsulanRingkas,
    SasaranUsulan,
)
from ..schemas.search import Domain, Order
from ..security import Principal

__all__ = [
    "SEARCHABLE_FIELDS",
    "AiUsulanService",
    "FungsiAiBelumAktifError",
    "PiiModeAiBelumDidukungError",
    "UsulanBelumBisaDiputusError",
    "UsulanBelumDiterimaError",
    "UsulanBerjalanError",
]

SEARCHABLE_FIELDS = frozenset(
    {"fungsi", "sasaran_jenis", "sasaran_id", "hasil_serap", "created_at"}
)
"""Field yang boleh dipakai pada domain search usulan AI; `isi` dan `amplop` tidak termasuk."""


class PiiModeAiBelumDidukungError(ConflictError):
    """409: `AI_PII_MODE` bukan `BLOKIR` (mode `SAMARKAN` belum dibuka)."""

    error_code = "pii_mode_belum_didukung"


class UsulanBerjalanError(ConflictError):
    """409: sasaran dan fungsi yang sama masih punya usulan yang belum diserap."""

    error_code = "usulan_berjalan"


class UsulanBelumBisaDiputusError(ConflictError):
    """409: usulan belum diserap, atau `hasil_serap`-nya bukan `USULAN_DIBUAT`/`EVIDENCE_GAP`."""

    error_code = "usulan_belum_bisa_diputus"


class UsulanBelumDiterimaError(ConflictError):
    """409: usulan belum diterima reviewer, jadi tidak boleh menjadi sumber fungsi lain.

    Diterima berarti putusan terakhirnya `APPROVE` (dengan `isi` terisi) atau `REVISE`.
    Kode galat huruf besar karena dipakai sebagai kontrak klien (rangkaian usulan P03, P07).
    """

    error_code = "USULAN_BELUM_DITERIMA"


class FungsiAiBelumAktifError(ConflictError):
    """409: fungsi belum terdaftar (`AI_FUNGSI_AKTIF`)."""

    error_code = "fungsi_belum_aktif"


class AiUsulanService(Protocol):
    """Kontrak tabel `ai_usulan`: pengajuan umum fungsi AI non-narasi."""

    def ajukan(
        self,
        fungsi: str,
        sasaran_jenis: SasaranUsulan,
        sasaran_id: str,
        sumber: list[SumberAi],
        parameter: dict[str, Any],
        principal: Principal,
        konteks_server: dict[str, Any] | None = None,
    ) -> AiUsulanRingkas:
        """Periksa gerbang, ajukan job lewat gateway, dan catat satu usulan.

        `konteks_server` adalah cuplikan yang diisi server (P07: `authorization_state`),
        disimpan apa adanya di `ai_usulan.konteks_server` dan tidak dikirim ke model.
        """
        ...

    def sumber_dari_usulan(self, usulan_id: str) -> SumberAi:
        """Bungkus usulan yang sudah diterima sebagai sumber `USULAN_AI` (`usulan:<id>`).

        Raises:
            NotFoundError: usulan tidak ada (404).
            UsulanBelumDiterimaError: putusan terakhir bukan `APPROVE`/`REVISE` (409).
        """
        ...

    def get(self, usulan_id: str) -> AiUsulanRead:
        """Ambil satu usulan lengkap dengan `isi`/`amplop`; `NotFoundError` (404) bila tak ada."""
        ...

    def putuskan(
        self, usulan_id: str, data: AiUsulanPutusanCreate, actor_key: str
    ) -> AiUsulanPutusanRead:
        """Catat satu putusan reviewer (append-only); tidak menyentuh narasi.

        Raises:
            NotFoundError: usulan tidak ada (404).
            UsulanBelumBisaDiputusError: belum diserap atau `MANUAL` (409).
        """
        ...

    def list(
        self,
        *,
        fungsi: str | None,
        sasaran_jenis: str | None,
        sasaran_id: str | None,
        hasil_serap: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AiUsulanRingkas], int]:
        """Daftar ringkas (tanpa `isi`/`amplop`), terbaru dulu, dengan filter opsional."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[AiUsulanRingkas], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`); hasil tanpa `isi`/`amplop`."""
        ...
