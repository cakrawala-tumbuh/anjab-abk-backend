"""Skema Pydantic untuk hasil analisis OPM."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OpmHasilTaskRead(BaseModel):
    """Hasil agregat satu task lintas responden."""

    model_config = ConfigDict(from_attributes=True)

    task_kode: str = Field(description="Kode task.", examples=["K001"])
    uraian_tugas: str = Field(description="Uraian tugas.")
    tugas_pokok: str = Field(description="Nama tugas pokok induk.")
    detil_tugas: str | None = Field(default=None, description="Nama detil tugas induk, bila ada.")
    n: int = Field(description="Jumlah responden yang menilai task ini.", examples=[3])
    mean_importance: float = Field(description="Rata-rata importance.", examples=[4.0])
    mean_frequency: float = Field(description="Rata-rata frequency.", examples=[3.0])
    mean_criticality: float = Field(description="Rata-rata criticality.", examples=[5.0])
    sd_importance: float | None = Field(
        default=None, description="Standar deviasi importance (None bila n < 2)."
    )
    sd_frequency: float | None = Field(
        default=None, description="Standar deviasi frequency (None bila n < 2)."
    )
    sd_criticality: float | None = Field(
        default=None, description="Standar deviasi criticality (None bila n < 2)."
    )
    selection_essential: bool = Field(
        description="True bila mean_importance >= 4 atau mean_criticality >= 4."
    )
    workload_essential: bool = Field(
        description=(
            "True bila (mean_importance >= 3 dan mean_frequency >= 3)"
            " atau mean_criticality >= 4."
        )
    )
    prop_selection_essential: float = Field(
        description=(
            "Proporsi responden yang menandai task ini selection-essential secara individual."
        )
    )
    prop_workload_essential: float = Field(
        description=(
            "Proporsi responden yang menandai task ini workload-essential secara individual."
        )
    )


class OpmHasilSesiRead(BaseModel):
    """Hasil analisis lengkap satu sesi OPM (seluruh task snapshot)."""

    model_config = ConfigDict(from_attributes=True)

    sesi_id: str = Field(description="ID sesi.")
    jabatan_id: str = Field(description="ID jabatan yang dinilai.")
    jabatan_nama: str | None = Field(default=None, description="Nama jabatan yang dinilai.")
    periode: str = Field(description="Periode survei.")
    n_responden_submit: int = Field(description="Jumlah responden yang sudah submit.")
    tasks: list[OpmHasilTaskRead] = Field(description="Hasil per task.")
