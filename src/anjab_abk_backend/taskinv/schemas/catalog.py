"""Skema Pydantic untuk catalog Task Inventory (master data, read-only)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .calhr import AiMode, Kondisi, SumberBukti, VaType


class TiCatalogRead(BaseModel):
    """Satu item catalog task yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    kode: str = Field(description="Kode task deterministik.", examples=["TIf0b59714"])
    unit: str = Field(description="Unit/jenjang (TK/SD/SMP/SMA).", examples=["TK"])
    jabatan_id: str = Field(description="ID jabatan.", examples=["jbt_a1b2c3d4"])
    tugas_pokok_id: str = Field(
        description="ID tugas pokok — kunci stabil untuk cascade Tahap 1 (level 1).",
        examples=["titp_a1b2c3d4"],
    )
    tugas_pokok: str = Field(description="Tugas pokok (klaster).", examples=["Pengelolaan SDM"])
    detil_tugas_id: str | None = Field(
        default=None,
        description=(
            "ID detil tugas — kunci stabil untuk cascade Tahap 1 (level 2); "
            "null bila task langsung di bawah tugas pokok."
        ),
        examples=["tidt_a1b2c3d4"],
    )
    detil_tugas: str | None = Field(
        default=None,
        description="Detil tugas (kelompok); null bila task langsung di bawah tugas pokok.",
        examples=["Mengevaluasi Kinerja Karyawan"],
    )
    uraian_tugas: str = Field(
        description="Uraian tugas (task statement).",
        examples=["Menyusun evaluasi karyawan"],
    )
    urutan: int = Field(description="Urutan dalam kombinasi unit × jabatan.", examples=[1])
    std_sumber_bukti: SumberBukti | None = None
    std_kondisi: Kondisi | None = None
    std_frekuensi_teks: str | None = None
    std_durasi_per_kali: str | None = None
    std_jam_per_minggu: float | None = None
    std_peak4w_hours: float | None = None
    std_ai_mode: AiMode | None = None
    std_va_type: VaType | None = None
    std_dcs_flag: bool | None = None


class TiKombinasiRead(BaseModel):
    """Satu kombinasi (unit × jabatan) beserta jumlah task."""

    model_config = ConfigDict(from_attributes=True)

    unit: str = Field(description="Unit/jenjang.", examples=["TK"])
    jabatan_id: str = Field(description="ID jabatan.", examples=["jbt_a1b2c3d4"])
    jabatan_nama: str = Field(description="Nama jabatan.", examples=["Kepala Sekolah"])
    jumlah_task: int = Field(description="Jumlah task pada kombinasi ini.", examples=[42])
