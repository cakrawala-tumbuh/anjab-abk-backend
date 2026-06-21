"""Skema Pydantic untuk himpunan task terpilih & hasil agregasi Task Inventory."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TiTaskTerpilihRead(BaseModel):
    """Satu task pada himpunan terpilih (beku setelah TAHAP2) + statistik relevansi."""

    model_config = ConfigDict(from_attributes=True)

    kode: str = Field(description="Kode task.", examples=["TIf0b59714"])
    tugas_pokok: str = Field(description="Tugas pokok.")
    detil_tugas: str = Field(description="Detil tugas.")
    uraian_tugas: str = Field(description="Uraian tugas.")
    n_relevan: int = Field(description="Jumlah partisipan yang menandai task ini relevan.")
    pct_relevan: float = Field(description="Persentase partisipan (terhadap submit Tahap 1).")


class TiHasilTaskRead(BaseModel):
    """Hasil agregasi satu task lintas responden (masukan ABK)."""

    model_config = ConfigDict(from_attributes=True)

    kode: str = Field(description="Kode task.")
    tugas_pokok: str = Field(description="Tugas pokok.")
    detil_tugas: str = Field(description="Detil tugas.")
    uraian_tugas: str = Field(description="Uraian tugas.")
    n_relevan: int = Field(description="Jumlah partisipan yang menandai relevan (Tahap 1).")
    pct_relevan: float = Field(description="Persentase relevansi (terhadap submit Tahap 1).")
    n_detail: int = Field(description="Jumlah partisipan yang mengisi detail (Tahap 2).")
    jam_per_minggu_mean: float = Field(description="Rata-rata jam/minggu antar responden.")
    jam_per_tahun_mean: float = Field(description="Rata-rata jam/tahun (jam/minggu × 45).")
    durasi_per_kali_mean: float = Field(description="Rata-rata durasi per pelaksanaan (menit).")
    peak4w_hours_mean: float = Field(description="Rata-rata jam pada 4 minggu peak.")
    ai_mode_dist: dict[str, int] = Field(description="Distribusi AI_Mode.")
    va_type_dist: dict[str, int] = Field(description="Distribusi VA_Type.")
    dcs_flag_count: int = Field(description="Jumlah responden yang menandai risiko DCS.")


class TiHasilSesiRead(BaseModel):
    """Hasil analisis lengkap satu sesi Task Inventory."""

    model_config = ConfigDict(from_attributes=True)

    sesi_id: str = Field(description="ID sesi.")
    unit: str = Field(description="Unit/jenjang.")
    kategori_jabatan: str = Field(description="Kategori jabatan.")
    periode: str = Field(description="Periode.")
    n_responden_tahap1: int = Field(description="Jumlah responden yang submit Tahap 1.")
    n_responden_tahap2: int = Field(description="Jumlah responden yang submit Tahap 2.")
    jumlah_task_terpilih: int = Field(description="Jumlah task pada himpunan terpilih.")
    total_jam_per_minggu: float = Field(description="Total rata-rata jam/minggu seluruh task.")
    total_jam_per_tahun: float = Field(description="Total rata-rata jam/tahun seluruh task.")
    tasks: list[TiHasilTaskRead] = Field(description="Hasil agregasi per task.")
