"""Skema masukan/keluaran `NarasiService`: aktor, kasus, versi, kutipan sumber, dan event."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .kasus import BasisRelation, EventKind, NarrativeKind, RevisionOrigin, StatusNarasi

AKTOR_AI_WORKER = "system:ai-worker"
"""Identitas proses AI (K-14): tanpa token, tidak pernah boleh mencatat event tinjauan."""


@dataclass(frozen=True)
class AktorNarasi:
    """Pelaku sebuah penulisan narasi, diturunkan dari token tervalidasi (bukan dari body).

    Attributes:
        key: Kunci aktor, mis. subject token atau `system:ai-worker`.
        role: Peran aktor saat bertindak (maks 40 karakter).
    """

    key: str
    role: str


class NarasiKasusCreate(BaseModel):
    """Payload kasus narasi baru; `status` awal selalu `SOURCE_CHECKED`."""

    model_config = ConfigDict(extra="forbid")

    instrument_id: str = Field(min_length=1, max_length=50)
    field_key: str = Field(min_length=1, max_length=100)
    peran_ref: str = Field(min_length=1, max_length=100)
    periode: str = Field(min_length=1, max_length=20)
    sekolah_id: str | None = Field(default=None, max_length=40)
    assignment_ref: str | None = Field(default=None, max_length=100)
    target_subject_ref: str | None = Field(default=None, max_length=100)
    konteks_kode: str | None = Field(default=None, max_length=100)
    narrative_kind: NarrativeKind
    intended_use: str = Field(min_length=1, max_length=200)
    permission_scope: str = Field(min_length=1, max_length=200)
    sensitivity_class: str = Field(min_length=1, max_length=40)


class NarasiKasusRead(BaseModel):
    """Kasus narasi beserta status proyeksinya."""

    id: str
    instrument_id: str
    field_key: str
    peran_ref: str
    periode: str
    sekolah_id: str | None
    assignment_ref: str | None
    target_subject_ref: str | None
    konteks_kode: str | None
    narrative_kind: NarrativeKind
    status: StatusNarasi
    intended_use: str
    permission_scope: str
    sensitivity_class: str
    dibuat_oleh: str
    created_at: datetime
    updated_at: datetime


class KutipanSumber(BaseModel):
    """Kutipan teks sumber yang mendasari sebuah versi."""

    model_config = ConfigDict(extra="forbid")

    sumber_id: str = Field(max_length=36)
    source_hash: str = Field(
        min_length=64, max_length=64, description="Harus sama dengan `narasi_sumber.teks_hash`."
    )
    basis_relation: BasisRelation
    source_span: str | None = None


class NarasiVersiRead(BaseModel):
    """Satu versi teks kasus narasi."""

    id: str
    narasi_id: str
    revision_no: int
    revision_origin: RevisionOrigin
    status_hasil: str
    teks: str | None
    supersedes_id: str | None
    ai_run_id: str | None
    output_hash: str | None
    metadata_ai: dict[str, Any] | None
    dibuat_oleh: str
    created_at: datetime


class NarasiEventRead(BaseModel):
    """Satu tindakan manusia yang tercatat pada sebuah kasus."""

    id: str
    narasi_id: str
    narasi_versi_id: str | None
    actor_key: str
    actor_role: str
    event_kind: EventKind
    dari_status: StatusNarasi
    ke_status: StatusNarasi
    event_notes: str | None
    event_at: datetime
