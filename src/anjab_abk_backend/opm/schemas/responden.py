"""Skema Pydantic untuk resource `OpmResponden`."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OpmRespondenCreate(BaseModel):
    """Payload pendaftaran responden manual ke dalam sesi OPM.

    `partisipan_id` wajib — responden OPM harus anggota SME panel jabatan sesi.
    """

    model_config = ConfigDict(extra="forbid")

    nama: str | None = Field(
        default=None,
        max_length=200,
        description="Nama responden (opsional).",
        examples=["Budi Santoso, S.Pd."],
    )
    jabatan_label: str = Field(
        min_length=1,
        max_length=200,
        description="Label jabatan responden (teks bebas).",
        examples=["Guru Matematika"],
    )
    partisipan_id: str = Field(
        min_length=1,
        description="ID partisipan yang wajib merupakan anggota SME panel jabatan sesi.",
        examples=["par_a1b2c3d4"],
    )


class OpmRespondenBulkCreate(BaseModel):
    """Payload penugasan (assign) responden OPM massal (bulk).

    `nama`/`jabatan_label` diresolusi otomatis dari `PartisipanModel`/`JabatanModel`
    (mengikuti pola auto-populate OPM saat sesi dibuat) — beda dari payload single
    yang mewajibkan `jabatan_label` diisi manual.
    """

    model_config = ConfigDict(extra="forbid")

    partisipan_ids: list[str] = Field(
        min_length=1,
        description="Daftar ID partisipan (wajib anggota SME panel jabatan sesi ini).",
        examples=[["par_a1b2c3d4", "par_e5f6g7h8"]],
    )


class OpmRespondenRead(BaseModel):
    """Representasi responden yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID responden.", examples=["oprs_a1b2c3d4"])
    sesi_id: str = Field(description="ID sesi induk.", examples=["opses_a1b2c3d4"])
    nama: str | None = Field(default=None, description="Nama responden.")
    jabatan_label: str = Field(description="Label jabatan responden.")
    partisipan_id: str | None = Field(
        default=None, description="ID partisipan yang terhubung, bila ada."
    )
    sudah_submit: bool = Field(description="True jika jawaban sudah disubmit.")
    submitted_at: datetime | None = Field(default=None, description="Waktu submit jawaban.")
    created_at: datetime = Field(description="Waktu pendaftaran (UTC, ISO-8601).")
