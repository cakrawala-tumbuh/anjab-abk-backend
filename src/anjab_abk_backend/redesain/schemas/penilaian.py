"""Skema Pydantic penilaian redesain (sheet PENILAIAN) beserta saran triase otomatis."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .kosakata import Indikasi, Skala, StatusBukti, YaTidak

_FIELD_READ_ONLY = ("saran_otomatis", "versi_aturan_triase")


def _buang_field_read_only(data: Any) -> Any:
    """Buang field hitungan sistem dari payload mentah agar diabaikan, bukan ditolak 422.

    Args:
        data: Payload mentah sebelum validasi.

    Returns:
        Payload tanpa `saran_otomatis`/`versi_aturan_triase` (bila berupa dict), atau
        `data` apa adanya.
    """
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k not in _FIELD_READ_ONLY}
    return data


class PenilaianCreate(BaseModel):
    """Payload penilaian baru untuk satu masalah (satu penilaian per masalah).

    `saran_otomatis` & `versi_aturan_triase` dihitung sistem; bila ikut dikirim, keduanya
    diabaikan (tidak 422). Field asing lain tetap ditolak (`extra="forbid"`).
    """

    model_config = ConfigDict(extra="forbid")

    masalah_id: str = Field(description="ID masalah redesain yang dinilai.")
    status_bukti: StatusBukti = Field(description="Status dengan bukti.")
    gap_material: YaTidak = Field(description="Apakah gap masih material.")
    indikasi_kritis: Indikasi = Field(description="Indikasi risiko kritis (istilah bagian E).")
    k1: Skala | None = Field(default=None, description="Skala kriteria K1; `null` = kosong.")
    k2: Skala | None = Field(default=None, description="Skala kriteria K2; `null` = kosong.")
    k3: Skala | None = Field(default=None, description="Skala kriteria K3; `null` = kosong.")
    k4: Skala | None = Field(default=None, description="Skala kriteria K4; `null` = kosong.")
    alasan_rentang_beda: str | None = None
    diluruskan_sekolah: str | None = Field(
        default=None, description="Ringkasan Tim: apa yang telah diluruskan sekolah."
    )
    pemeriksa_sekolah_konteks: str | None = None
    tindak_lanjut: str | None = None
    catatan_sumber_versi: str | None = None

    @model_validator(mode="before")
    @classmethod
    def abaikan_field_read_only(cls, data: Any) -> Any:
        """Abaikan field hitungan sistem kiriman klien (lihat docstring kelas)."""
        return _buang_field_read_only(data)


class PenilaianUpdate(BaseModel):
    """Payload ubah parsial penilaian. `masalah_id` tidak dapat diubah.

    Field nullable boleh dikosongkan dengan `null`; field wajib (`status_bukti`,
    `gap_material`, `indikasi_kritis`) yang dikirim `null` diabaikan. Field hitungan sistem
    diabaikan seperti pada `PenilaianCreate`.
    """

    model_config = ConfigDict(extra="forbid")

    status_bukti: StatusBukti | None = None
    gap_material: YaTidak | None = None
    indikasi_kritis: Indikasi | None = None
    k1: Skala | None = None
    k2: Skala | None = None
    k3: Skala | None = None
    k4: Skala | None = None
    alasan_rentang_beda: str | None = None
    diluruskan_sekolah: str | None = None
    pemeriksa_sekolah_konteks: str | None = None
    tindak_lanjut: str | None = None
    catatan_sumber_versi: str | None = None

    @model_validator(mode="before")
    @classmethod
    def abaikan_field_read_only(cls, data: Any) -> Any:
        """Abaikan field hitungan sistem kiriman klien (lihat docstring kelas)."""
        return _buang_field_read_only(data)


class PenilaianRead(BaseModel):
    """Satu penilaian redesain beserta saran triase hasil hitungan sistem."""

    id: str = Field(description="ID penilaian (UUID v4).")
    masalah_id: str
    status_bukti: StatusBukti
    gap_material: YaTidak
    indikasi_kritis: Indikasi
    k1: Skala | None
    k2: Skala | None
    k3: Skala | None
    k4: Skala | None
    alasan_rentang_beda: str | None
    diluruskan_sekolah: str | None
    pemeriksa_sekolah_konteks: str | None
    tindak_lanjut: str | None
    catatan_sumber_versi: str | None
    saran_otomatis: str | None = Field(
        description="Saran triase otomatis (read-only).", examples=["P1 - Utama"]
    )
    versi_aturan_triase: str = Field(description="Versi aturan triase.", examples=["v1.3"])
    created_at: datetime
    updated_at: datetime
