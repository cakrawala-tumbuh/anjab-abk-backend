"""Skema register run AI: status teknis, rujukan sumber, dan proyeksi baca."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["AiRunRead", "AiSumber", "StatusQaAi"]


class StatusQaAi(StrEnum):
    """Status teknis sebuah run AI (bukan status narasi P-20)."""

    MENUNGGU = "MENUNGGU"
    LOLOS = "LOLOS"
    KARANTINA = "KARANTINA"
    EVIDENCE_GAP = "EVIDENCE_GAP"
    DIBLOKIR = "DIBLOKIR"
    GAGAL = "GAGAL"


class AiSumber(BaseModel):
    """Rujukan satu sumber data yang dipakai run: id dan hash isinya (bukan isinya)."""

    source_id: str = Field(description="Id sumber data.", examples=["bukti-123"])
    source_hash: str = Field(description="SHA-256 isi sumber.", examples=["ab" * 32])


class AiRunRead(BaseModel):
    """Satu baris register run AI. Tidak memuat ``masukan`` maupun ``keluaran``."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="UUID v4 run (ModelRun_ID).")
    fungsi: str = Field(description="Fungsi AI yang dipanggil.", examples=["draf_narasi"])
    prompt_version: str = Field(description="Versi instruksi (prompt).", examples=["v1"])
    prompt_hash: str = Field(description="SHA-256 prompt yang dipakai.")
    model_diminta: str = Field(description="Model yang diminta pemanggil.")
    model_dilayani: str | None = Field(default=None, description="Model yang benar-benar melayani.")
    penyedia: str | None = Field(
        default=None,
        description="Mode penyedia (`API_ANTHROPIC`/`LANGGANAN_CLAUDE`/`MATI`) saat run diajukan, "
        "ditimpa mode yang dipakai tepat sebelum model dipanggil; null pada run lama.",
    )
    protocol_id: str = Field(description="Protocol_ID: arm/versi aplikasi+commit/fungsi@prompt.")
    input_snapshot_id: str = Field(description="SHA-256 kanonik masukan (sidik jari data).")
    sumber: list[AiSumber] = Field(description="Sumber data beserta hash-nya.")
    status_qa: StatusQaAi = Field(description="Status teknis run.")
    kode_qa: list[str] = Field(description="Kode hasil pemeriksaan QA.")
    stop_reason: str | None = Field(default=None, description="Alasan model berhenti.")
    input_tokens: int | None = Field(default=None, description="Jumlah token masukan.")
    output_tokens: int | None = Field(default=None, description="Jumlah token keluaran.")
    dibuat_oleh: str | None = Field(default=None, description="Subjek pemicu run.")
    created_at: datetime = Field(description="Waktu run dibuka (UTC).")
    selesai_at: datetime | None = Field(default=None, description="Waktu run ditutup (UTC).")
