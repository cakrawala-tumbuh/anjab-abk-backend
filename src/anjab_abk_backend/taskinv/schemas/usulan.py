"""Skema Pydantic untuk usulan uraian tugas tambahan dari partisipan Tahap 1.

Lihat `taskinv/services/usulan.py` untuk kontrak seam akses data dan
`api/v1/taskinv_usulan.py` untuk endpoint yang memakai skema ini.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TiUsulanCreate(BaseModel):
    """Payload pembuatan usulan uraian tugas baru oleh responden Tahap 1.

    Ditulis di bawah tugas pokok (dan opsional detil tugas) pilihan responden —
    tanpa induk, usulan tidak bisa ditempatkan saat konsensus Tahap 2. Hanya sah saat
    sesi berstatus `TAHAP1` dan responden belum `tahap1_submit` (lihat endpoint).
    """

    model_config = ConfigDict(extra="forbid")

    tugas_pokok_id: str = Field(
        description="ID tugas pokok induk usulan ini; harus terkait jabatan sesi.",
        examples=["titp_a1b2c3d4"],
    )
    detil_tugas_id: str | None = Field(
        default=None,
        description="ID detil tugas induk (opsional); bila diisi, harus turunan tugas_pokok_id.",
        examples=["tidt_a1b2c3d4"],
    )
    uraian: str = Field(
        min_length=1,
        max_length=500,
        description="Teks uraian tugas yang diusulkan responden.",
        examples=["Menyiapkan materi ajar tambahan untuk kelas inklusi."],
    )


class TiUsulanRead(BaseModel):
    """Representasi satu usulan uraian tugas, dengan nama induk sudah di-resolve.

    `tugas_pokok`/`detil_tugas` diresolusi live dari `TugasPokokService`/
    `DetilTugasService` — bukan disimpan sebagai kolom (tabel `ti_usulan_task` hanya
    menyimpan id-nya) — supaya klien tidak perlu memanggil katalog lagi untuk
    menampilkan nama induk.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID usulan.", examples=["tius_a1b2c3d4"])
    sesi_id: str = Field(description="ID sesi Task Inventory.", examples=["tises_a1b2c3d4"])
    responden_id: str = Field(description="ID responden pengusul.", examples=["trsp_a1b2c3d4"])
    tugas_pokok_id: str = Field(description="ID tugas pokok induk.")
    tugas_pokok: str = Field(description="Nama tugas pokok induk (ter-resolve).")
    detil_tugas_id: str | None = Field(default=None, description="ID detil tugas induk (bila ada).")
    detil_tugas: str | None = Field(
        default=None, description="Nama detil tugas induk (ter-resolve, bila ada)."
    )
    uraian: str = Field(description="Teks uraian tugas yang diusulkan.")
    disetujui: bool | None = Field(
        default=None,
        description="Keputusan koordinator Tahap 2. NULL = belum diputuskan.",
    )
    task_kode: str | None = Field(
        default=None,
        description="Kode task hasil materialisasi ke katalog (diisi saat mulai-tahap3).",
    )
    created_at: datetime = Field(description="Waktu usulan dibuat.")
