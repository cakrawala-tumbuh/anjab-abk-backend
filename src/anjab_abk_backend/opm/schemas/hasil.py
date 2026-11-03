"""Skema Pydantic untuk hasil analisis OPM."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ...schemas.common import CabangSesi


class OpmHasilTaskRead(BaseModel):
    """Hasil agregat satu task lintas responden."""

    model_config = ConfigDict(from_attributes=True)

    task_kode: str = Field(description="Kode task.", examples=["K001"])
    uraian_tugas: str = Field(description="Uraian tugas.")
    tugas_pokok: str = Field(description="Nama tugas pokok induk.")
    detil_tugas: str | None = Field(default=None, description="Nama detil tugas induk, bila ada.")
    n: int = Field(description="Jumlah responden yang menilai task ini.", examples=[3])
    mean_importance: float | None = Field(
        default=None, description="Rata-rata importance (null bila n == 0).", examples=[4.0]
    )
    mean_frequency: float | None = Field(
        default=None, description="Rata-rata frequency (null bila n == 0).", examples=[3.0]
    )
    mean_criticality: float | None = Field(
        default=None, description="Rata-rata criticality (null bila n == 0).", examples=[5.0]
    )
    sd_importance: float | None = Field(
        default=None, description="Standar deviasi importance (None bila n < 2)."
    )
    sd_frequency: float | None = Field(
        default=None, description="Standar deviasi frequency (None bila n < 2)."
    )
    sd_criticality: float | None = Field(
        default=None, description="Standar deviasi criticality (None bila n < 2)."
    )
    selection_essential: bool | None = Field(
        default=None,
        description="True bila mean_importance >= 4 atau mean_criticality >= 4 (null bila n == 0).",
    )
    workload_essential: bool | None = Field(
        default=None,
        description=(
            "True bila (mean_importance >= 3 dan mean_frequency >= 3)"
            " atau mean_criticality >= 4 (null bila n == 0)."
        ),
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
    orphan: bool = Field(
        default=False,
        description="True bila task ini punya baris di register pengecualian sesi.",
    )


class OpmHasilSesiRead(BaseModel):
    """Hasil analisis lengkap satu sesi OPM (seluruh task snapshot)."""

    model_config = ConfigDict(from_attributes=True)

    sesi_id: str = Field(description="ID sesi.")
    jabatan_id: str = Field(description="ID jabatan yang dinilai.")
    jabatan_nama: str | None = Field(default=None, description="Nama jabatan yang dinilai.")
    cabang: CabangSesi | None = Field(
        default=None, description="Cabang lokasi kajian (echo dari `OpmSesiRead.cabang`)."
    )
    periode: str = Field(description="Periode survei.")
    n_responden_submit: int = Field(description="Jumlah responden yang sudah submit.")
    tasks: list[OpmHasilTaskRead] = Field(description="Hasil per task.")
