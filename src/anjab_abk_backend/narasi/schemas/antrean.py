"""Skema rute antrean tinjauan Tim: `/api/v1/narasi/antrean` dan `/narasi/kasus/{id}/tinjauan`."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .kasus import BasisRelation, NarrativeKind, RevisionOrigin, StatusNarasi
from .rute import BATAS_TEKS_REVISI, SumberRevisiItem

STATUS_ANTREAN: tuple[StatusNarasi, ...] = (
    StatusNarasi.AI_DRAFT,
    StatusNarasi.TEAM_REVIEW,
    StatusNarasi.NEED_FACT,
)
"""Status kasus yang tampil di antrean reviewer; selain ini bukan antrean."""

PAPARAN_TIDAK_BERLAKU = "TIDAK_BERLAKU"
"""Nilai tetap `paparan` pada F1; penanda paparan baru bermakna untuk F2."""

CATATAN_MIN = 5
"""Panjang minimum `catatan` pada aksi `TOLAK` dan `BUTUH_SUMBER`."""


class StatusAntrean(StrEnum):
    """Filter status antrean; hanya tiga status yang menunggu tinjauan."""

    AI_DRAFT = "AI_DRAFT"
    TEAM_REVIEW = "TEAM_REVIEW"
    NEED_FACT = "NEED_FACT"


class AksiTinjauan(StrEnum):
    """Aksi reviewer; label tombol: Terima, Koreksi, Tolak, Butuh sumber."""

    TERIMA = "TERIMA"
    KOREKSI = "KOREKSI"
    TOLAK = "TOLAK"
    BUTUH_SUMBER = "BUTUH_SUMBER"


class AntreanItemRead(BaseModel):
    """Satu baris antrean: ringkasan kasus dan versi terbarunya, tanpa teks."""

    narasi_id: str
    instrument_id: str
    field_key: str
    peran_ref: str
    periode: str
    narrative_kind: NarrativeKind
    status: StatusNarasi
    versi_id: str
    revision_no: int
    revision_origin: RevisionOrigin
    label_dokumenter: Any | None = Field(default=None, description="Dari `metadata_ai`.")
    jumlah_sumber: int
    jumlah_kontradiksi: int
    updated_at: datetime


class AntreanSumberRead(BaseModel):
    """Sumber sebuah versi, lengkap dengan teks untuk tampilan berdampingan dengan draf."""

    sumber_id: str
    judul: str
    versi: str
    source_span: str | None
    source_hash: str
    basis_relation: BasisRelation
    teks: str


class AntreanDetailRead(BaseModel):
    """Detail satu kasus antrean: versi terbaru, sumber, dan metadata AI terpilih."""

    narasi_id: str
    instrument_id: str
    field_key: str
    peran_ref: str
    periode: str
    narrative_kind: NarrativeKind
    status: StatusNarasi
    versi_id: str
    revision_no: int
    revision_origin: RevisionOrigin
    teks: str | None
    ai_run_id: str | None
    sumber: list[AntreanSumberRead]
    contradictions: list[Any]
    unknowns: list[Any]
    missing_facts: list[Any]
    claim_to_source_map: Any | None
    recommended_review_scope: Any | None
    paparan: str = Field(default=PAPARAN_TIDAK_BERLAKU)


class TinjauanCreate(BaseModel):
    """Badan `POST /narasi/kasus/{id}/tinjauan`. Kunci tak dikenal (mis. aktor) diabaikan."""

    model_config = ConfigDict(extra="ignore")

    aksi: AksiTinjauan
    narasi_versi_id: str = Field(min_length=1, max_length=36)
    catatan: str | None = Field(default=None, max_length=2000)
    teks: str | None = Field(default=None, min_length=1, max_length=BATAS_TEKS_REVISI)
    sumber: list[SumberRevisiItem] | None = None
