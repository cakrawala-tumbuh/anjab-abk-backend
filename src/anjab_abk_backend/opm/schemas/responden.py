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


class OpmRespondenAlihkan(BaseModel):
    """Payload pengalihan kepemilikan responden OPM ke partisipan lain (admin).

    Backlog `anjab-abk-backend#47` — memindahkan baris responden (beserta seluruh
    jawaban `opm_jawaban` yang merujuk `responden_id`, bukan `partisipan_id`) dari
    `dari_partisipan_id` ke `ke_partisipan_id` tanpa mengisi ulang.
    `dari_partisipan_id` adalah guard eksplisit: request ditolak (422) bila bukan
    pemilik aktual responden ini saat ini.
    """

    model_config = ConfigDict(extra="forbid")

    dari_partisipan_id: str = Field(
        min_length=1,
        description="ID partisipan pemilik responden saat ini (guard eksplisit).",
        examples=["par_5c0a6908"],
    )
    ke_partisipan_id: str = Field(
        min_length=1,
        description="ID partisipan tujuan pengalihan.",
        examples=["par_f57e0ceb"],
    )


class OpmRespondenRead(BaseModel):
    """Representasi responden yang dikembalikan API."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID responden.", examples=["oprs_a1b2c3d4"])
    sesi_id: str = Field(description="ID sesi induk.", examples=["opses_a1b2c3d4"])
    kode_orang: str | None = Field(
        default=None,
        description=(
            "Kode orang pseudonim responden (`O-nnnn`, sama dengan register redesain);"
            " null bila responden tidak terhubung ke partisipan."
        ),
        examples=["O-0012"],
    )
    jabatan_label: str = Field(description="Label jabatan responden.")
    partisipan_id: str | None = Field(
        default=None, description="ID partisipan yang terhubung, bila ada."
    )
    sudah_submit: bool = Field(description="True jika jawaban sudah disubmit.")
    submitted_at: datetime | None = Field(default=None, description="Waktu submit jawaban.")
    created_at: datetime = Field(description="Waktu pendaftaran (UTC, ISO-8601).")
