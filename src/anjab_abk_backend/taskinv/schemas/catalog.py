"""Skema Pydantic untuk catalog Task Inventory (master data, read-only)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TiCatalogRead(BaseModel):
    """Satu item catalog task yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    kode: str = Field(description="Kode task deterministik.", examples=["TIf0b59714"])
    unit: str = Field(description="Unit/jenjang (TK/SD/SMP/SMA).", examples=["TK"])
    kategori_jabatan: str = Field(description="Kategori jabatan.", examples=["Kepala Sekolah"])
    tugas_pokok: str = Field(description="Tugas pokok (klaster).", examples=["Pengelolaan SDM"])
    detil_tugas: str = Field(
        description="Detil tugas (kelompok).", examples=["Mengevaluasi Kinerja Karyawan"]
    )
    uraian_tugas: str = Field(
        description="Uraian tugas (task statement).",
        examples=["Menyusun evaluasi karyawan"],
    )
    urutan: int = Field(description="Urutan dalam kombinasi unit×kategori.", examples=[1])


class TiKombinasiRead(BaseModel):
    """Satu kombinasi (unit × kategori jabatan) beserta jumlah task."""

    model_config = ConfigDict(from_attributes=True)

    unit: str = Field(description="Unit/jenjang.", examples=["TK"])
    kategori_jabatan: str = Field(description="Kategori jabatan.", examples=["Kepala Sekolah"])
    jumlah_task: int = Field(description="Jumlah task pada kombinasi ini.", examples=[42])
