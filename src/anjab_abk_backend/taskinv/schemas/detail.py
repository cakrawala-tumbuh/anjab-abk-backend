"""Skema Pydantic untuk detailing Tahap 2 (field CalHR 5-komponen per task)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .calhr import Kondisi, SumberBukti, VaType


class TiDetailItem(BaseModel):
    """Field detail CalHR untuk satu task relevan.

    Sejak backlog `anjab-abk-backend#38`, kelima field CalHR inti
    (`sumber_bukti`/`kondisi`/`frekuensi_teks`/`durasi_per_kali`/`va_type`) bersifat
    **opsional** agar draft parsial (baru mengisi sebagian task) dapat disimpan lewat
    `PUT .../detail` tanpa ditolak `422`. Kelengkapan seluruh field baru ditegakkan saat
    finalisasi (`POST .../detail/submit`, lihat `TiDetailService.submit`). Batas nilai yang
    ada (`min_length`/`max_length`/`ge`) tetap berlaku untuk nilai non-null; `None` melewati
    validasi itu apa adanya.
    """

    model_config = ConfigDict(extra="forbid")

    task_kode: str = Field(description="Kode task (harus ada di himpunan terpilih).")
    sumber_bukti: SumberBukti | None = Field(default=None, description="Formal/Aktual/Keduanya.")
    kondisi: Kondisi | None = Field(default=None, description="Baseline/Peak/Both.")
    frekuensi_teks: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Frekuensi (Harian/Mingguan/Bulanan/dst).",
    )
    durasi_per_kali: int | None = Field(
        default=None, ge=0, description="Durasi per pelaksanaan (menit)."
    )
    jam_per_minggu: float = Field(
        default=0.0, ge=0, description="Estimasi jam per minggu (tidak lagi diisi partisipan)."
    )
    peak4w_hours: float = Field(default=0.0, ge=0, description="Jam pada 4 minggu peak.")
    va_type: VaType | None = Field(default=None, description="VA-Core/VA-Enable/NVA-Residual.")
    setuju_standar: bool = Field(
        default=True, description="True bila partisipan menerima nilai standar master apa adanya."
    )
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
    """Representasi satu entri detail Tahap 2.

    Kelima field CalHR inti bertipe `| None` sejak `anjab-abk-backend#38`: entri draft
    parsial (belum lengkap) melapor `null` pada field yang belum diisi alih-alih memaksa
    nilai palsu. Payload lama yang sudah lengkap tetap sah tanpa perubahan (pelonggaran murni).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID entri detail.", examples=["tdet_a1b2c3d4"])
    responden_id: str = Field(description="ID responden.")
    sesi_id: str = Field(description="ID sesi.")
    task_kode: str = Field(description="Kode task.")
    sumber_bukti: SumberBukti | None = None
    kondisi: Kondisi | None = None
    frekuensi_teks: str | None = None
    durasi_per_kali: int | None = None
    jam_per_minggu: float
    peak4w_hours: float
    va_type: VaType | None = None
    setuju_standar: bool
    catatan: str | None = None
