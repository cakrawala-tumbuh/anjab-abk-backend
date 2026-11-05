"""Enum domain kasus narasi dan versinya (`narasi_kasus`, `narasi_versi`, `narasi_versi_sumber`).

Nilai disimpan sebagai string di kolom (tanpa enum DB); kamus nilainya dijaga skema Pydantic
dan CHECK constraint pada migrasi.
"""

from __future__ import annotations

from enum import StrEnum


class NarrativeKind(StrEnum):
    """Jenis narasi: F1 dokumen formal s.d. F5 riset."""

    F1_FORMAL = "F1_FORMAL"
    F2_ACTUAL = "F2_ACTUAL"
    F3_HANDOFF = "F3_HANDOFF"
    F4_ANALYTICAL = "F4_ANALYTICAL"
    F5_RESEARCH = "F5_RESEARCH"


class StatusNarasi(StrEnum):
    """Status siklus tinjauan sebuah kasus narasi (14 nilai); proyeksi, boleh berubah."""

    SOURCE_CHECKED = "SOURCE_CHECKED"
    AI_DRAFT = "AI_DRAFT"
    NEED_FACT = "NEED_FACT"
    TEAM_REVIEW = "TEAM_REVIEW"
    TEAM_VERIFIED = "TEAM_VERIFIED"
    SUBJECT_REVIEW = "SUBJECT_REVIEW"
    SUBJECT_CONFIRMED = "SUBJECT_CONFIRMED"
    SUBJECT_CORRECTION = "SUBJECT_CORRECTION"
    SUBJECT_REJECTED = "SUBJECT_REJECTED"
    SUBJECT_UNCERTAIN = "SUBJECT_UNCERTAIN"
    FINAL_TEAM_REVIEW = "FINAL_TEAM_REVIEW"
    RELEASED_FACT = "RELEASED_FACT"
    RELEASED_LIMITED = "RELEASED_LIMITED"
    RETURN_FOR_CLARIFICATION = "RETURN_FOR_CLARIFICATION"


class EventKind(StrEnum):
    """Jenis tindakan manusia pada tabel `narasi_event` (11 nilai paket)."""

    TEAM_APPROVE = "TEAM_APPROVE"
    TEAM_REVISE = "TEAM_REVISE"
    TEAM_REJECT = "TEAM_REJECT"
    NEED_SOURCE = "NEED_SOURCE"
    SUBJECT_CONFIRM = "SUBJECT_CONFIRM"
    SUBJECT_CORRECT = "SUBJECT_CORRECT"
    SUBJECT_REJECT = "SUBJECT_REJECT"
    SUBJECT_UNSURE = "SUBJECT_UNSURE"
    FINAL_TEAM_APPROVE = "FINAL_TEAM_APPROVE"
    RELEASE_LIMITED = "RELEASE_LIMITED"
    RETURN_CLARIFICATION = "RETURN_CLARIFICATION"


class RevisionOrigin(StrEnum):
    """Asal sebuah versi narasi."""

    AI_DRAFT = "AI_DRAFT"
    HUMAN_CORRECTION = "HUMAN_CORRECTION"
    AI_REVISION = "AI_REVISION"
    REVIEWER_EDIT = "REVIEWER_EDIT"
    ORIGINAL_QUOTE = "ORIGINAL_QUOTE"


class BasisRelation(StrEnum):
    """Hubungan kutipan sumber terhadap isi versi narasi."""

    DIRECT = "DIRECT"
    CONTEXT = "CONTEXT"
    CONTRADICTS = "CONTRADICTS"
    UNKNOWN = "UNKNOWN"


METADATA_AI_KUNCI: tuple[str, ...] = (
    "claim_to_source_map",
    "missing_facts",
    "contradictions",
    "unknowns",
    "recommended_review_scope",
    "label_dokumenter",
    "confidence_reason",
)
"""Satu-satunya kunci yang boleh ada pada `narasi_versi.metadata_ai`."""
