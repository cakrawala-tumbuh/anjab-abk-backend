"""Skema Pydantic penilaian redesain (sheet PENILAIAN) beserta saran triase otomatis."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .kosakata import (
    Indikasi,
    PrioritasFinal,
    Skala,
    StatusBukti,
    StatusPenilaian,
    StatusPenilaianManual,
    YaTidak,
)

_WIB = timezone(timedelta(hours=7))

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


def hari_ini_wib() -> date:
    """Tanggal hari ini menurut WIB (UTC+7), acuan batas "tanggal keputusan tak di masa depan"."""
    return datetime.now(UTC).astimezone(_WIB).date()


class Peringatan(BaseModel):
    """Satu peringatan hitungan (tidak disimpan) atas keputusan prioritas final."""

    kode: str = Field(description="Kode peringatan.", examples=["PRIORITAS_TANPA_BUKTI"])
    pesan: str = Field(description="Penjelasan untuk Tim Kajian.")


class PenilaianPutuskan(BaseModel):
    """Payload keputusan prioritas final oleh Tim Kajian (boleh diulang).

    Alasan selalu wajib (kosong/spasi → 422), baik prioritas final sama maupun beda dari
    saran. Tanggal keputusan tidak boleh di masa depan (acuan WIB).
    """

    model_config = ConfigDict(extra="forbid")

    prioritas_final: PrioritasFinal = Field(description="Prioritas final keputusan Tim Kajian.")
    alasan_final: str = Field(min_length=1, description="Alasan keputusan (wajib).")
    pemutus_kode_orang: str = Field(
        min_length=1, max_length=20, description="Kode orang pemutus (mis. `O-0001`)."
    )
    pemutus_jabatan: str = Field(min_length=1, max_length=200, description="Jabatan pemutus.")
    tanggal_keputusan: date = Field(description="Tanggal keputusan; tidak di masa depan.")

    @field_validator("alasan_final", "pemutus_kode_orang", "pemutus_jabatan")
    @classmethod
    def tidak_kosong(cls, v: str) -> str:
        """Tolak teks yang hanya berisi spasi; kembalikan teks yang sudah di-strip."""
        v = v.strip()
        if not v:
            raise ValueError("Tidak boleh kosong.")
        return v

    @field_validator("tanggal_keputusan")
    @classmethod
    def bukan_masa_depan(cls, v: date) -> date:
        """Tolak tanggal setelah hari ini (WIB)."""
        if v > hari_ini_wib():
            raise ValueError("Tanggal keputusan tidak boleh di masa depan.")
        return v


class PenilaianStatus(BaseModel):
    """Payload ubah status penilaian; `Telah diputuskan` hanya lewat aksi putuskan (422)."""

    model_config = ConfigDict(extra="forbid")

    status_penilaian: StatusPenilaianManual = Field(description="Status baru penilaian.")


class SebaranK(BaseModel):
    """Sebaran jawaban K1–K4 konfirmasi terkirim (tak digantikan) atas satu masalah.

    Tiap `k1`…`k4` memetakan `Tinggi`/`Sedang`/`Rendah`/`Belum tahu`/`kosong` ke hitungan.
    Sengaja tanpa rata-rata atau skor.
    """

    masalah_id: str
    jumlah_konfirmasi: int = Field(description="Jumlah konfirmasi terkirim yang dihitung.")
    k1: dict[str, int]
    k2: dict[str, int]
    k3: dict[str, int]
    k4: dict[str, int]


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
    prioritas_final: PrioritasFinal | None = None
    alasan_final: str | None = None
    pemutus_kode_orang: str | None = None
    pemutus_jabatan: str | None = None
    tanggal_keputusan: date | None = None
    saran_saat_keputusan: str | None = Field(
        default=None, description="`saran_otomatis` pada saat keputusan terakhir dibuat."
    )
    status_penilaian: StatusPenilaian = "Belum ditelaah"
    peringatan: list[Peringatan] = Field(
        default_factory=list, description="Peringatan hitungan (tidak disimpan, tidak memblokir)."
    )
    created_at: datetime
    updated_at: datetime
