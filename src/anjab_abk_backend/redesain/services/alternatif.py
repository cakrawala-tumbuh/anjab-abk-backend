"""SEAM akses data alternatif redesain (sheet ALTERNATIF)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from ...errors import ConflictError, ValidationAppError
from ...schemas.search import Domain, Order
from ..schemas.alternatif import (
    AlternatifCreate,
    AlternatifRead,
    AlternatifUpdate,
    KeputusanPerubahanCreate,
    KeputusanPerubahanRead,
    KesiapanCreate,
    KesiapanMatriksRead,
    KesiapanRead,
    PenerimaCreate,
    PenerimaRead,
    StatusKesiapan,
)

SEARCHABLE_FIELDS = frozenset({"id", "kode", "masalah_id", "opsi", "status_telaah"})
"""Field yang boleh dipakai pada domain search alternatif."""


class PenerimaGandaError(ConflictError):
    """409: jabatan itu sudah menjadi penerima alternatif yang sama."""

    error_code = "PENERIMA_GANDA"


class KesiapanBelumReadyError(ConflictError):
    """409: APPROVE ditolak karena status opsi pada periode itu bukan READY."""

    error_code = "KESIAPAN_BELUM_READY"


class KesiapanHoldError(ConflictError):
    """409: CONDITIONAL ditolak karena status opsi pada periode itu HOLD."""

    error_code = "KESIAPAN_HOLD"


class PenerimaBukanMilikAlternatifError(ValidationAppError):
    """422: `penerima_id` bukan penerima milik alternatif pada URL."""

    error_code = "PENERIMA_BUKAN_MILIK_ALTERNATIF"


def hitung_status_opsi(
    penerima: Iterable[tuple[bool, StatusKesiapan | None]],
) -> StatusKesiapan:
    """Hitung status opsi satu alternatif pada satu periode dari status tiap penerima.

    Fungsi murni (tanpa I/O), dipakai ulang oleh item lanjutan.

    Args:
        penerima: Pasangan `(material, status_terakhir)` per penerima; status `None` berarti
            belum dinilai pada periode itu.

    Returns:
        `HOLD` bila tanpa penerima, atau ada penerima material berstatus HOLD / belum dinilai;
        selain itu `CONDITIONAL` bila ada penerima (apa pun materialnya) berstatus CONDITIONAL;
        selain itu `READY`. Penerima non-material yang HOLD/belum dinilai tidak berpengaruh.
    """
    daftar = list(penerima)
    if not daftar:
        return StatusKesiapan.HOLD
    for material, status in daftar:
        if material and status in (None, StatusKesiapan.HOLD):
            return StatusKesiapan.HOLD
    if any(status == StatusKesiapan.CONDITIONAL for _, status in daftar):
        return StatusKesiapan.CONDITIONAL
    return StatusKesiapan.READY


class AlternatifService(Protocol):
    """Kontrak alternatif redesain. Sengaja TIDAK punya `delete`."""

    def create(self, data: AlternatifCreate, *, pelaku_kode_orang: str | None) -> AlternatifRead:
        """Buat alternatif (kode `U-NNN` dibangkitkan) dan catat riwayat.

        Raises:
            ValidationAppError: masalah/jabatan/kode orang tak dikenal, atau aturan
                opsi/status dilanggar (422).
            ConflictError: kode hasil bangkitan bentrok (409).
        """
        ...

    def get(self, alternatif_id: str) -> AlternatifRead:
        """Ambil satu alternatif; `NotFoundError` bila tak ada."""
        ...

    def list(self, *, limit: int, offset: int) -> tuple[list[AlternatifRead], int]:
        """Daftar berurutan menurut `kode`."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[AlternatifRead], int]:
        """Cari memakai domain ala Odoo (field: `SEARCHABLE_FIELDS`)."""
        ...

    def update(
        self, alternatif_id: str, data: AlternatifUpdate, *, pelaku_kode_orang: str | None
    ) -> AlternatifRead:
        """Ubah parsial dan catat riwayat; aturan divalidasi pada keadaan akhir."""
        ...

    def tambah_penerima(self, alternatif_id: str, data: PenerimaCreate) -> PenerimaRead:
        """Tambah penerima (jabatan) pada alternatif.

        Raises:
            NotFoundError: alternatif tak ada (404).
            ValidationAppError: jabatan tak dikenal (422).
            PenerimaGandaError: jabatan sudah menjadi penerima alternatif ini (409).
        """
        ...

    def daftar_penerima(self, alternatif_id: str) -> list[PenerimaRead]:
        """Daftar penerima alternatif, urut `created_at` naik; 404 bila alternatif tak ada."""
        ...

    def nilai_kesiapan(
        self, alternatif_id: str, data: KesiapanCreate, *, dinilai_oleh: str
    ) -> KesiapanRead:
        """Simpan penilaian kesiapan baru (append-only).

        Raises:
            NotFoundError: alternatif tak ada (404).
            PenerimaBukanMilikAlternatifError: `penerima_id` milik alternatif lain/tak ada (422).
        """
        ...

    def matriks_kesiapan(self, alternatif_id: str, periode: str) -> KesiapanMatriksRead:
        """Matriks kesiapan pada `periode` (penilaian terakhir per penerima) + status opsi.

        Raises:
            NotFoundError: alternatif tak ada (404).
        """
        ...

    def putuskan_perubahan(
        self, alternatif_id: str, data: KeputusanPerubahanCreate, *, pemutus: str
    ) -> KeputusanPerubahanRead:
        """Catat keputusan perubahan (append-only) setelah menegakkannya terhadap status opsi.

        Aturan: `APPROVE` hanya bila status opsi READY; `CONDITIONAL` hanya bila READY atau
        CONDITIONAL; `HOLD` dan `REJECT` selalu boleh.

        Raises:
            NotFoundError: alternatif tak ada (404).
            KesiapanBelumReadyError: APPROVE saat status opsi bukan READY (409).
            KesiapanHoldError: CONDITIONAL saat status opsi HOLD (409).
        """
        ...

    def riwayat_keputusan_perubahan(
        self, alternatif_id: str, periode: str | None
    ) -> list[KeputusanPerubahanRead]:
        """Riwayat keputusan perubahan urut `created_at` naik lalu `id`; filter `periode` opsional.

        Keputusan berlaku = baris terakhir per periode.

        Raises:
            NotFoundError: alternatif tak ada (404).
        """
        ...
