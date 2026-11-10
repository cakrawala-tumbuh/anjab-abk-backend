"""SEAM akses data katalog konteks redesain."""

from __future__ import annotations

from typing import Protocol

from ...errors import ConflictError, ValidationAppError
from ...schemas.common import ErrorDetail
from ...schemas.search import Domain, Order
from ..schemas.konteks import KonteksCreate, KonteksRead, KonteksUpdate, TerapkanKonteks

SEARCHABLE_FIELDS = frozenset(
    {"id", "kode", "tema", "gelombang", "aktif", "ai_usulan_id", "created_at", "updated_at"}
)
"""Field domain search konteks; `ai_usulan_id` agar klien dapat menandai kandidat terterapkan."""


class UsulanBukanP11Error(ValidationAppError):
    """422: usulan bukan keluaran P11 atau sasarannya bukan `REDESAIN_KONTEKS`."""

    error_code = "USULAN_BUKAN_P11"


class KandidatTakAdaError(ValidationAppError):
    """422: `indeks_kandidat` di luar rentang `isi.konteks_candidates`, atau `isi` null."""

    error_code = "KANDIDAT_TAK_ADA"


class IsianRevisiWajibError(ValidationAppError):
    """422: putusan terakhir `REVISE` tetapi keempat isian teks tidak dikirim lengkap."""

    error_code = "ISIAN_REVISI_WAJIB"


class KandidatSudahDiterapkanError(ConflictError):
    """409: kandidat ini sudah menjadi konteks; `details[0].msg` memuat `konteks_id`-nya.

    Klien membaca id konteks yang sudah ada dari `details[0]` (`code` =
    `KANDIDAT_SUDAH_DITERAPKAN`, `loc` = `["konteks_id"]`, `msg` = id konteks).
    """

    error_code = "KANDIDAT_SUDAH_DITERAPKAN"

    def __init__(self, konteks_id: str | None) -> None:
        """Bangun galat dengan rincian id konteks yang sudah ada (bila diketahui).

        Args:
            konteks_id: Id konteks hasil penerapan sebelumnya; None bila tak terbaca
                (mis. bentrok UNIQUE dari permintaan bersamaan yang belum terlihat).
        """
        super().__init__(
            "Kandidat ini sudah diterapkan menjadi konteks.",
            details=(
                [
                    ErrorDetail(
                        loc=["konteks_id"],
                        msg=konteks_id,
                        type="conflict",
                        code=self.error_code,
                    )
                ]
                if konteks_id
                else None
            ),
        )


class KonteksService(Protocol):
    """Kontrak katalog konteks. Sengaja TIDAK punya `delete` (gunakan `aktif=false`)."""

    def create(self, data: KonteksCreate, *, pelaku_kode_orang: str | None) -> KonteksRead:
        """Buat konteks dan catat riwayat; `ConflictError` bila `kode` duplikat."""
        ...

    def get(self, konteks_id: str) -> KonteksRead:
        """Ambil satu konteks; `NotFoundError` bila tak ada."""
        ...

    def list(self, *, limit: int, offset: int) -> tuple[list[KonteksRead], int]:
        """Daftar berurutan menurut `kode`."""
        ...

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[KonteksRead], int]:
        """Cari memakai domain ala Odoo."""
        ...

    def update(
        self, konteks_id: str, data: KonteksUpdate, *, pelaku_kode_orang: str | None
    ) -> KonteksRead:
        """Ubah parsial dan catat riwayat."""
        ...

    def terapkan_usulan(
        self, usulan_id: str, data: TerapkanKonteks, *, pelaku_kode_orang: str | None
    ) -> KonteksRead:
        """Buat SATU konteks baru dari satu kandidat usulan P11 yang sudah diterima.

        Satu transaksi: baca usulan, validasi, insert konteks bertanda asal, catat riwayat
        `create`. Tidak mengubah usulan maupun putusannya.

        Raises:
            NotFoundError: usulan tidak ada (404).
            UsulanBukanP11Error: fungsi bukan P11 / sasaran bukan `REDESAIN_KONTEKS` (422).
            UsulanBelumDiterimaError: putusan terakhir bukan `APPROVE`/`REVISE` (409).
            KandidatTakAdaError: indeks di luar rentang atau `isi` null (422).
            IsianRevisiWajibError: putusan `REVISE` tanpa keempat isian (422).
            KandidatSudahDiterapkanError: kandidat sudah menjadi konteks (409).
            ConflictError: `kode` konteks sudah dipakai (409 `conflict`).
        """
        ...
