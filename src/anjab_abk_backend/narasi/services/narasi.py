"""SEAM satu-satunya jalur tulis kasus, versi, dan event narasi, plus mesin status tahap Tim.

Aturan di sini berhenti di `TEAM_VERIFIED`: tahap subjek, finalisasi, dan rilis belum dibuka.
"""

from __future__ import annotations

from typing import Any, Protocol

from ...errors import ConflictError, ValidationAppError
from ...schemas.search import Domain, Order
from ..schemas.antrean import AntreanItemRead, AntreanSumberRead
from ..schemas.kasus import EventKind, RevisionOrigin, StatusNarasi
from ..schemas.mesin import (
    AktorNarasi,
    KutipanSumber,
    NarasiEventRead,
    NarasiKasusCreate,
    NarasiKasusRead,
    NarasiVersiRead,
)
from ..schemas.rute import NarasiVersiSumberRead

SEARCHABLE_FIELDS_KASUS = frozenset(
    {"status", "instrument_id", "field_key", "periode", "narrative_kind", "created_at"}
)
"""Field yang boleh dipakai pada domain search kasus narasi."""

S = StatusNarasi

TRANSISI_NARASI: dict[StatusNarasi, frozenset[StatusNarasi]] = {
    S.SOURCE_CHECKED: frozenset({S.AI_DRAFT, S.NEED_FACT, S.TEAM_REVIEW}),
    S.AI_DRAFT: frozenset({S.TEAM_VERIFIED, S.TEAM_REVIEW, S.SOURCE_CHECKED, S.NEED_FACT}),
    S.TEAM_REVIEW: frozenset({S.TEAM_VERIFIED, S.TEAM_REVIEW, S.SOURCE_CHECKED, S.NEED_FACT}),
    S.NEED_FACT: frozenset({S.AI_DRAFT, S.NEED_FACT, S.TEAM_REVIEW}),
    S.TEAM_VERIFIED: frozenset({S.TEAM_REVIEW}),
}
"""Perpindahan status sah pada tahap Tim; status lain tidak punya jalan keluar/masuk."""

EVENT_TAHAP_TIM: dict[EventKind, StatusNarasi] = {
    EventKind.TEAM_APPROVE: S.TEAM_VERIFIED,
    EventKind.TEAM_REVISE: S.TEAM_REVIEW,
    EventKind.TEAM_REJECT: S.SOURCE_CHECKED,
    EventKind.NEED_SOURCE: S.NEED_FACT,
}
"""Event yang sudah dibuka (tahap Tim) dan status tujuannya; kind lain belum dibuka."""

STATUS_HASIL_VERSI: frozenset[StatusNarasi] = frozenset({S.AI_DRAFT, S.NEED_FACT, S.TEAM_REVIEW})
"""Nilai `status_hasil` yang boleh dihasilkan sebuah versi baru."""


class EventBelumDibukaError(ConflictError):
    """409: jenis event di luar tahap Tim (belum dibuka)."""

    error_code = "event_belum_dibuka"


class LingkupGandaError(ConflictError):
    """409: lingkup kasus yang sama sudah ada."""

    error_code = "narasi_lingkup_ganda"


class JenisBelumDibukaError(ValidationAppError):
    """422: `narrative_kind` selain `F1_FORMAL` belum dibuka pada jalur manual."""

    error_code = "narasi_jenis_belum_dibuka"


class SensitifBelumDibukaError(ValidationAppError):
    """422: kasus `SENSITIF` belum dibuka."""

    error_code = "narasi_sensitif_belum_dibuka"


class VersiBasiError(ConflictError):
    """409: `supersedes_id`/`narasi_versi_id` bukan versi terbaru kasus (cek `expected_version`)."""

    error_code = "versi_basi"


class TransisiTidakSahError(ConflictError):
    """409: perpindahan status di luar `TRANSISI_NARASI`."""

    error_code = "transisi_tidak_sah"


class NarasiTidakDalamAntreanError(ConflictError):
    """409: kasus tidak berstatus `AI_DRAFT`/`TEAM_REVIEW`/`NEED_FACT`."""

    error_code = "narasi_tidak_dalam_antrean"


class NarasiTanpaTeksError(ConflictError):
    """409: aksi `TERIMA` atas versi terbaru tanpa teks (kasus `NEED_FACT`)."""

    error_code = "narasi_tanpa_teks"


class NarasiService(Protocol):
    """Kontrak tulis narasi; semua metode memindahkan status dalam transaksi yang sama."""

    def buat_kasus(self, data: NarasiKasusCreate, aktor: AktorNarasi) -> NarasiKasusRead:
        """Buat kasus berstatus `SOURCE_CHECKED`.

        Raises:
            ConflictError: lingkup kasus yang sama sudah ada.
        """
        ...

    def tambah_versi(
        self,
        narasi_id: str,
        *,
        revision_origin: RevisionOrigin,
        status_hasil: StatusNarasi,
        teks: str | None,
        sumber: list[KutipanSumber],
        supersedes_id: str | None,
        aktor: AktorNarasi,
        ai_run_id: str | None = None,
        output_hash: str | None = None,
        metadata_ai: dict[str, Any] | None = None,
    ) -> NarasiVersiRead:
        """Tambah versi baru dan pindahkan status kasus ke `status_hasil`."""
        ...

    def catat_event(
        self,
        narasi_id: str,
        narasi_versi_id: str | None,
        event_kind: EventKind,
        aktor: AktorNarasi,
        catatan: str | None,
    ) -> NarasiEventRead:
        """Catat tindakan manusia tahap Tim dan pindahkan status kasus."""
        ...

    def get_kasus(self, narasi_id: str) -> NarasiKasusRead:
        """Ambil satu kasus; `NotFoundError` bila tak ada."""
        ...

    def list_kasus(
        self,
        *,
        status: str | None,
        instrument_id: str | None,
        periode: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[NarasiKasusRead], int]:
        """Daftar kasus, terbaru dulu, dengan filter opsional."""
        ...

    def search_kasus(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[NarasiKasusRead], int]:
        """Cari kasus memakai domain ala Odoo (field: `SEARCHABLE_FIELDS_KASUS`)."""
        ...

    def versi_terbaru(self, narasi_id: str) -> NarasiVersiRead | None:
        """Versi ber-`revision_no` tertinggi kasus, atau `None` bila belum ada."""
        ...

    def daftar_versi(self, narasi_id: str) -> list[NarasiVersiRead]:
        """Seluruh versi kasus, urut `revision_no` naik."""
        ...

    def sumber_versi(self, narasi_versi_id: str) -> list[NarasiVersiSumberRead]:
        """Tautan sumber sebuah versi (tanpa teks sumber)."""
        ...

    def daftar_event(self, narasi_id: str) -> list[NarasiEventRead]:
        """Seluruh event kasus, urut waktu naik."""
        ...

    def list_antrean(
        self,
        *,
        status: str | None,
        instrument_id: str | None,
        periode: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AntreanItemRead], int]:
        """Antrean reviewer: kasus `AI_DRAFT`/`TEAM_REVIEW`/`NEED_FACT`, `updated_at` naik."""
        ...

    def sumber_lengkap_versi(self, narasi_versi_id: str) -> list[AntreanSumberRead]:
        """Sumber sebuah versi beserta judul, versi, dan teksnya."""
        ...
