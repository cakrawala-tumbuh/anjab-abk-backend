"""Skema permintaan draf AI atas kasus narasi (`narasi_ai_permintaan`)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...schemas.async_job import StatusJob

BATAS_SUMBER_PERMINTAAN = 50
"""Jumlah maksimum `sumber_ids` pada satu permintaan."""


class PermintaanAiCreate(BaseModel):
    """Badan `POST /narasi/kasus/{id}/draf-ai`.

    `sumber_ids` boleh kosong: sumber kosong berakhir `NEED_FACT` tanpa memanggil model.
    """

    model_config = ConfigDict(extra="forbid")

    sumber_ids: list[str] = Field(
        default_factory=list,
        max_length=BATAS_SUMBER_PERMINTAAN,
        description="Id sumber narasi yang diajukan; boleh kosong.",
    )


class KritikAiCreate(BaseModel):
    """Badan `POST /narasi/kasus/{id}/kritik-ai`.

    Hanya mengacu satu versi; teks draf tidak pernah dikirim klien, server membacanya dari
    versi itu supaya ikut gerbang PII.
    """

    model_config = ConfigDict(extra="forbid")

    narasi_versi_id: str = Field(
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
        max_length=36,
        description="Id versi narasi yang dikritik; harus versi terbaru kasus.",
    )


class EkstraksiAiCreate(BaseModel):
    """Badan `POST /narasi/sumber/{id}/ekstraksi-ai`.

    Hanya dua kode konteks; tidak ada teks bebas (parameter berada di luar gerbang PII).
    """

    model_config = ConfigDict(extra="forbid")

    peran_ref: str = Field(
        pattern=r"^[A-Za-z0-9_.:-]+$", max_length=100, description="Kode peran konteks ekstraksi."
    )
    periode: str = Field(
        pattern=r"^[A-Za-z0-9_.:-]+$", max_length=100, description="Kode periode konteks."
    )


class TanyaBuktiAiCreate(BaseModel):
    """Badan `POST /narasi/kasus/{id}/tanya-bukti-ai`.

    `klaim` dan `keputusan_terkait` adalah teks bebas; server mengirimnya ke model sebagai
    sumber (bukan `parameter`) agar ikut gerbang PII. Spasi tepi dipangkas sebelum panjang
    diperiksa. `sumber_ids` wajib berisi minimal satu id.
    """

    model_config = ConfigDict(extra="forbid")

    klaim: str = Field(
        min_length=5,
        max_length=2000,
        description="Klaim yang buktinya dinilai (5-2.000 karakter, spasi tepi dipangkas).",
    )
    keputusan_terkait: str = Field(
        min_length=5,
        max_length=500,
        description="Keputusan yang bergantung pada klaim (5-500 karakter, spasi tepi dipangkas).",
    )
    sumber_ids: list[str] = Field(
        min_length=1,
        max_length=BATAS_SUMBER_PERMINTAAN,
        description="Id sumber narasi yang menjadi materi bukti; minimal satu.",
    )

    @field_validator("klaim", "keputusan_terkait", mode="before")
    @classmethod
    def _pangkas(cls, nilai: object) -> object:
        """Pangkas spasi tepi sebelum batas panjang diperiksa."""
        return nilai.strip() if isinstance(nilai, str) else nilai


class PermintaanAiRead(BaseModel):
    """Satu permintaan draf AI beserta status job-nya; tanpa `masukan` dan `keluaran`."""

    id: str = Field(description="UUID v4 permintaan.")
    job_id: str = Field(description="Id job asinkron.")
    job_status: StatusJob = Field(description="Status job saat dibaca.")
    job_error_code: str | None = Field(description="Kode galat job bila ada.")
    ai_run_id: str = Field(description="Id run pada register `ai_run`.")
    sumber_ids: list[str] = Field(description="Sumber yang diajukan, urut pengajuan.")
    created_at: datetime
    diserap_at: datetime | None = Field(description="Terisi saat hasil run diserap.")
    hasil_serap: str | None
    kode_serap: list[str] | None
