"""Skema Pydantic untuk resource `UraianTugas` (master data catalog TI).

UraianTugas adalah pernyataan tugas spesifik (task statement) level terbawah.
Relasi M2O: UraianTugas → TugasPokok (via tugas_pokok_id),
            UraianTugas → DetilTugas (via detil_tugas_id, opsional),
            UraianTugas → Jabatan (via jabatan_id, M2O langsung).

Jabatan yang dapat dipilih untuk UraianTugas adalah jabatan yang tergabung
dalam jabatan_ids DetilTugas induknya (bila detil_tugas_id diisi).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .calhr import Kondisi, SumberBukti, VaType


class UraianTugasCreate(BaseModel):
    """Payload pembuatan uraian tugas."""

    model_config = ConfigDict(extra="forbid")

    kode: str = Field(
        min_length=1,
        max_length=20,
        description="Kode task deterministik (unik).",
        examples=["TIf0b59714"],
    )
    uraian: str = Field(
        min_length=1,
        max_length=500,
        description="Pernyataan tugas (task statement).",
        examples=["Menyusun evaluasi karyawan"],
    )
    unit: str = Field(
        min_length=1,
        max_length=20,
        description="Unit/jenjang (TK, SD, SMP, SMA, SMK, dll.).",
        examples=["TK"],
    )
    urutan: int = Field(
        ge=1,
        description="Urutan dalam kombinasi unit × jabatan.",
        examples=[1],
    )
    jabatan_id: str = Field(
        min_length=1,
        description=(
            "ID jabatan untuk uraian tugas ini (M2O). "
            "Bila detil_tugas_id diisi, jabatan harus ada dalam jabatan_ids DetilTugas tersebut."
        ),
        examples=["jbt_a1b2c3d4"],
    )
    detil_tugas_id: str | None = Field(
        default=None,
        description="ID detil tugas induk (M2O). Null jika task tidak masuk detil tugas.",
        examples=["dt_a1b2c3d4"],
    )
    tugas_pokok_id: str = Field(
        description="ID tugas pokok induk (M2O).",
        examples=["tp_a1b2c3d4"],
    )
    std_sumber_bukti: SumberBukti | None = Field(
        default=None, description="Nilai standar sumber bukti (prefill Tahap 3)."
    )
    std_kondisi: Kondisi | None = Field(default=None, description="Nilai standar kondisi.")
    std_frekuensi_teks: str | None = Field(
        default=None, max_length=100, description="Nilai standar frekuensi."
    )
    std_durasi_per_kali: str | None = Field(
        default=None,
        max_length=100,
        description="Nilai standar durasi per pelaksanaan (teks bebas).",
    )
    std_jam_per_minggu: float | None = Field(
        default=None, ge=0, description="Nilai standar jam per minggu."
    )
    std_peak4w_hours: float | None = Field(
        default=None, ge=0, description="Nilai standar jam pada 4 minggu peak."
    )
    std_va_type: VaType | None = Field(default=None, description="Nilai standar VA type.")


class UraianTugasUpdate(BaseModel):
    """Payload pembaruan sebagian uraian tugas."""

    model_config = ConfigDict(extra="forbid")

    kode: str | None = Field(default=None, min_length=1, max_length=20, description="Kode baru.")
    uraian: str | None = Field(
        default=None, min_length=1, max_length=500, description="Pernyataan tugas baru."
    )
    unit: str | None = Field(default=None, min_length=1, max_length=20, description="Unit baru.")
    urutan: int | None = Field(default=None, ge=1, description="Urutan baru.")
    jabatan_id: str | None = Field(default=None, min_length=1, description="ID jabatan baru.")
    detil_tugas_id: str | None = Field(default=None, description="ID detil tugas induk baru.")
    tugas_pokok_id: str | None = Field(default=None, description="ID tugas pokok induk baru.")
    std_sumber_bukti: SumberBukti | None = Field(
        default=None, description="Nilai standar sumber bukti (prefill Tahap 3)."
    )
    std_kondisi: Kondisi | None = Field(default=None, description="Nilai standar kondisi.")
    std_frekuensi_teks: str | None = Field(
        default=None, max_length=100, description="Nilai standar frekuensi."
    )
    std_durasi_per_kali: str | None = Field(
        default=None,
        max_length=100,
        description="Nilai standar durasi per pelaksanaan (teks bebas).",
    )
    std_jam_per_minggu: float | None = Field(
        default=None, ge=0, description="Nilai standar jam per minggu."
    )
    std_peak4w_hours: float | None = Field(
        default=None, ge=0, description="Nilai standar jam pada 4 minggu peak."
    )
    std_va_type: VaType | None = Field(default=None, description="Nilai standar VA type.")


class UraianTugasRead(BaseModel):
    """Representasi uraian tugas yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID unik uraian tugas.", examples=["ut_a1b2c3d4"])
    kode: str = Field(description="Kode task deterministik.", examples=["TIf0b59714"])
    uraian: str = Field(
        description="Pernyataan tugas (task statement).", examples=["Menyusun evaluasi karyawan"]
    )
    unit: str = Field(description="Unit/jenjang.", examples=["TK"])
    jabatan_id: str = Field(
        description="ID jabatan untuk uraian tugas ini (M2O langsung).",
        examples=["jbt_a1b2c3d4"],
    )
    urutan: int = Field(description="Urutan dalam kombinasi unit × jabatan.", examples=[1])
    detil_tugas_id: str | None = Field(
        default=None, description="ID detil tugas induk.", examples=["dt_a1b2c3d4"]
    )
    tugas_pokok_id: str = Field(description="ID tugas pokok induk.", examples=["tp_a1b2c3d4"])
    std_sumber_bukti: SumberBukti | None = Field(
        default=None, description="Nilai standar sumber bukti (prefill Tahap 3)."
    )
    std_kondisi: Kondisi | None = Field(default=None, description="Nilai standar kondisi.")
    std_frekuensi_teks: str | None = Field(
        default=None, max_length=100, description="Nilai standar frekuensi."
    )
    std_durasi_per_kali: str | None = Field(
        default=None,
        max_length=100,
        description="Nilai standar durasi per pelaksanaan (teks bebas).",
    )
    std_jam_per_minggu: float | None = Field(
        default=None, ge=0, description="Nilai standar jam per minggu."
    )
    std_peak4w_hours: float | None = Field(
        default=None, ge=0, description="Nilai standar jam pada 4 minggu peak."
    )
    std_va_type: VaType | None = Field(default=None, description="Nilai standar VA type.")
    created_at: datetime = Field(description="Waktu pembuatan (UTC, ISO-8601).")
