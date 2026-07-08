"""Skema Pydantic untuk detailing Tahap 2 (field CalHR 5-komponen per task)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SumberBukti = Literal["Formal", "Aktual", "Keduanya"]
Kondisi = Literal["Baseline", "Peak", "Both"]
AiMode = Literal["Human-led", "Co-Pilot", "AI-assisted"]
VaType = Literal["VA-Core", "VA-Enable", "NVA-Residual"]


class TiDetailItem(BaseModel):
    """Field detail CalHR untuk satu task relevan."""

    model_config = ConfigDict(extra="forbid")

    task_kode: str = Field(description="Kode task (harus ada di himpunan terpilih).")
    sumber_bukti: SumberBukti = Field(description="Formal/Aktual/Keduanya.")
    kondisi: Kondisi = Field(description="Baseline/Peak/Both.")
    frekuensi_teks: str = Field(
        min_length=1, max_length=100, description="Frekuensi (Harian/Mingguan/Bulanan/dst)."
    )
    durasi_per_kali: int = Field(ge=0, description="Durasi per pelaksanaan (menit).")
    jam_per_minggu: float = Field(ge=0, description="Estimasi jam per minggu.")
    peak4w_hours: float = Field(default=0.0, ge=0, description="Jam pada 4 minggu peak.")
    ai_mode: AiMode = Field(description="Human-led/Co-Pilot/AI-assisted.")
    va_type: VaType = Field(description="VA-Core/VA-Enable/NVA-Residual.")
    dcs_flag: bool = Field(default=False, description="True bila ada risiko DCS.")
    catatan: str | None = Field(default=None, max_length=500, description="Catatan ambiguitas.")


class TiDetailUpsert(BaseModel):
    """Payload draft-save (upsert parsial) detail Tahap 3 untuk satu responden.

    Boleh 0..N entri; tiap entri di-upsert per `task_kode`, dan wajib termasuk
    himpunan terpilih sesi. Kelengkapan minimal (≥1 entri) divalidasi terpisah
    saat finalisasi (`POST .../detail/submit`).
    """

    model_config = ConfigDict(extra="forbid")

    detail: list[TiDetailItem] = Field(
        default_factory=list, description="Daftar entri detail parsial, satu per task relevan."
    )


class TiDetailRead(BaseModel):
    """Representasi satu entri detail Tahap 2."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID entri detail.", examples=["tdet_a1b2c3d4"])
    responden_id: str = Field(description="ID responden.")
    sesi_id: str = Field(description="ID sesi.")
    task_kode: str = Field(description="Kode task.")
    sumber_bukti: SumberBukti
    kondisi: Kondisi
    frekuensi_teks: str
    durasi_per_kali: int
    jam_per_minggu: float
    peak4w_hours: float
    ai_mode: AiMode
    va_type: VaType
    dcs_flag: bool
    catatan: str | None = None
