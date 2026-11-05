"""Definisi fungsi AI P10: draf narasi formal F1 (kandidat dokumenter).

P10 menyusun draf narasi dari sumber yang diberikan. Hasilnya hanya kandidat
dokumenter untuk reviewer manusia, bukan pernyataan bahwa tugas aktual
terlaksana. Field amplop (``status``, ``source_refs``, ``cited_spans``, dll.)
berasal dari ``skema_dengan_amplop`` dan tidak diulang pada ``skema_isi``;
``model_run_id``, ``prompt_version``, ``model_version``, dan ``input_snapshot_id``
dicap server, bukan diisi model.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .gateway import FungsiAi

__all__ = ["FUNGSI_P10", "INSTRUKSI_P10", "SKEMA_ISI_P10", "ParameterP10"]

_POLA_PARAMETER = r"^[A-Za-z0-9_.:-]+$"

INSTRUKSI_P10 = """\
Fungsi: menyusun draf narasi formal F1 dari sumber yang diberikan.

Aturan fungsi:
1. Susun draf hanya dari sumber yang diberikan; jangan memakai pengetahuan lain.
2. Narasi F1 adalah DOCUMENTARY_CANDIDATE (kandidat dokumenter). Jangan menyatakan \
bahwa tugas aktual telah terlaksana.
3. Jangan mengarang angka, volume, atau waktu yang tidak tertulis di sumber.
4. Setiap klaim pada draf harus tercantum di claim_to_source_map beserta source_id \
dan kutipan span persis dari sumber itu.
5. Bila sumber tidak cukup, set status=EVIDENCE_GAP dan draft_text=null, lalu isi \
missing_facts dan unknowns dengan hal yang belum diketahui.
6. Jangan mengisi persetujuan, izin, skor, atau keputusan.
7. Tulis seluruh keluaran dalam bahasa Indonesia.\
"""

SKEMA_ISI_P10: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "narrative_kind",
        "draft_text",
        "claim_to_source_map",
        "missing_facts",
        "recommended_review_scope",
        "label_dokumenter",
    ],
    "properties": {
        "narrative_kind": {"type": "string", "enum": ["F1_FORMAL"]},
        "draft_text": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "claim_to_source_map": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["claim", "source_id", "span"],
                "properties": {
                    "claim": {"type": "string"},
                    "source_id": {"type": "string"},
                    "span": {"type": "string"},
                },
            },
        },
        "missing_facts": {"type": "array", "items": {"type": "string"}},
        "recommended_review_scope": {"type": "string"},
        "label_dokumenter": {"type": "string", "enum": ["DOCUMENTARY_CANDIDATE"]},
    },
}
"""Skema field ``isi`` P10: tanpa ``if/then``, ``minLength``, ``minItems``."""

FUNGSI_P10 = FungsiAi(
    kode="P10",
    prompt_version="p10-1",
    instruksi=INSTRUKSI_P10,
    skema_isi=SKEMA_ISI_P10,
)
"""Definisi fungsi P10 untuk katalog."""


class ParameterP10(BaseModel):
    """Parameter pengajuan P10.

    Hanya token pendek berpola ``^[A-Za-z0-9_.:-]+$``; tidak ada teks bebas
    karena ``parameter`` berada di luar gerbang PII.

    Attributes:
        narrative_kind: Jenis narasi; hanya ``F1_FORMAL``.
        instrument_id: Pengenal instrumen sasaran.
        field_key: Kunci isian sasaran.
        periode: Periode sasaran.
    """

    model_config = ConfigDict(extra="forbid")

    narrative_kind: Literal["F1_FORMAL"]
    instrument_id: str = Field(pattern=_POLA_PARAMETER, max_length=100)
    field_key: str = Field(pattern=_POLA_PARAMETER, max_length=100)
    periode: str = Field(pattern=_POLA_PARAMETER, max_length=100)
