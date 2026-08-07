"""Skema Pydantic untuk resource `OpmJawaban`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OpmJawabanItem(BaseModel):
    """Satu jawaban rating task dalam bulk submission.

    Ketiga dimensi (`importance`/`frequency`/`criticality`) boleh `null` — draft
    rating parsial disimpan apa adanya oleh `PUT .../jawaban`; kelengkapan
    ketiganya baru ditegakkan saat finalisasi (`POST .../jawaban/submit`).
    """

    model_config = ConfigDict(extra="forbid")

    task_kode: str = Field(
        description="Kode task orisinal (dari snapshot Task Inventory).",
        examples=["K001"],
    )
    importance: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description=(
            "Seberapa penting (1 Tidak penting … 5 Sangat penting). "
            "Boleh `null` pada draft — ketiga dimensi baru wajib terisi saat submit "
            "(`POST .../jawaban/submit`)."
        ),
        examples=[4],
    )
    frequency: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description=(
            "Seberapa sering (1 Insidental … 5 Sangat sering/Harian). "
            "Boleh `null` pada draft — ketiga dimensi baru wajib terisi saat submit "
            "(`POST .../jawaban/submit`)."
        ),
        examples=[3],
    )
    criticality: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description=(
            "Dampak jika gagal (1 Dampak minimal … 5 Dampak kritis). "
            "Boleh `null` pada draft — ketiga dimensi baru wajib terisi saat submit "
            "(`POST .../jawaban/submit`)."
        ),
        examples=[5],
    )
    catatan: str | None = Field(default=None, max_length=500, description="Catatan opsional.")


class OpmJawabanUpsert(BaseModel):
    """Payload draft-save (upsert parsial) rating untuk satu responden.

    Boleh 0..N item; tiap item di-upsert per `task_kode`. Kelengkapan set
    `task_kode` (harus persis sama dengan snapshot task sesi) divalidasi
    terpisah saat finalisasi (`POST .../jawaban/submit`).
    """

    model_config = ConfigDict(extra="forbid")

    jawaban: list[OpmJawabanItem] = Field(
        default_factory=list, description="Rating parsial untuk task dalam snapshot sesi."
    )


class OpmJawabanRead(BaseModel):
    """Representasi satu jawaban yang dikembalikan API.

    Ketiga dimensi bisa `null` selama baris masih berstatus draft (belum
    dilengkapi dan/atau belum submit).
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="ID jawaban.", examples=["opjw_a1b2c3d4"])
    responden_id: str = Field(description="ID responden.", examples=["oprs_a1b2c3d4"])
    task_kode: str = Field(description="Kode task orisinal.", examples=["K001"])
    importance: int | None = Field(default=None, description="Skor importance 1–5, atau `null`.")
    frequency: int | None = Field(default=None, description="Skor frequency 1–5, atau `null`.")
    criticality: int | None = Field(default=None, description="Skor criticality 1–5, atau `null`.")
    catatan: str | None = Field(default=None, description="Catatan.")
