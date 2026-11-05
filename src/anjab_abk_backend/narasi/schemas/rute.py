"""Skema rute `/api/v1/narasi/kasus`: badan permintaan Tim dan respons detail/riwayat."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .kasus import BasisRelation, NarrativeKind
from .mesin import NarasiEventRead, NarasiKasusRead, NarasiVersiRead

BATAS_TEKS_REVISI = 200_000
"""Batas karakter `teks` pada satu revisi manual."""


class SensitivityClass(StrEnum):
    """Kelas kepekaan kasus; hanya `NONPRIBADI` yang dibuka pada jalur manual."""

    NONPRIBADI = "NONPRIBADI"
    SENSITIF = "SENSITIF"


class NarasiKasusBuat(BaseModel):
    """Badan `POST /narasi/kasus`. Kunci tak dikenal (mis. `dibuat_oleh`) diabaikan.

    Aktor selalu dari token; `status` awal selalu `SOURCE_CHECKED`.
    """

    model_config = ConfigDict(extra="ignore")

    instrument_id: str = Field(min_length=1, max_length=50)
    field_key: str = Field(min_length=1, max_length=100)
    peran_ref: str = Field(min_length=1, max_length=100)
    periode: str = Field(min_length=1, max_length=20)
    sekolah_id: str | None = Field(default=None, max_length=40)
    assignment_ref: str | None = Field(default=None, max_length=100)
    target_subject_ref: str | None = Field(default=None, max_length=100)
    konteks_kode: str | None = Field(default=None, max_length=100)
    narrative_kind: NarrativeKind = Field(description="Hanya `F1_FORMAL` yang dibuka.")
    intended_use: str = Field(min_length=1, max_length=200)
    permission_scope: str = Field(min_length=1, max_length=200)
    sensitivity_class: SensitivityClass = Field(description="Hanya `NONPRIBADI` yang dibuka.")


class SumberRevisiItem(BaseModel):
    """Satu kutipan sumber pada revisi; hash dicocokkan server dari sumber tersimpan."""

    model_config = ConfigDict(extra="ignore")

    sumber_id: str = Field(min_length=1, max_length=36)
    source_span: str | None = None
    basis_relation: BasisRelation


class NarasiRevisiCreate(BaseModel):
    """Badan `POST /narasi/kasus/{id}/revisi`; asal dan status hasil ditetapkan service."""

    model_config = ConfigDict(extra="ignore")

    teks: str = Field(min_length=1, max_length=BATAS_TEKS_REVISI)
    sumber: list[SumberRevisiItem] = Field(min_length=1)
    supersedes_id: str | None = Field(
        default=None, max_length=36, description="Versi terbaru saat ini; kosong untuk versi 1."
    )


class NarasiVersiSumberRead(BaseModel):
    """Tautan versi ke sumber (tanpa teks sumber)."""

    sumber_id: str
    source_span: str | None
    source_hash: str
    basis_relation: BasisRelation


class NarasiVersiLengkap(NarasiVersiRead):
    """Versi beserta tautan sumbernya."""

    sumber: list[NarasiVersiSumberRead]


class NarasiKasusDetail(NarasiKasusRead):
    """Kasus beserta versi terbaru (bila ada); sumber ada di `versi_terbaru.sumber`."""

    versi_terbaru: NarasiVersiLengkap | None


class NarasiRiwayatRead(BaseModel):
    """Seluruh versi (urut `revision_no`) dan event (urut waktu) satu kasus."""

    versi: list[NarasiVersiLengkap]
    event: list[NarasiEventRead]
