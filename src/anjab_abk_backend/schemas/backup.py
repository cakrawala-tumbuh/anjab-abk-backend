"""Skema respons operasi restore basis data (backlog 025)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RestoreResult(BaseModel):
    """Hasil `POST /api/v1/system/restore`.

    `peringatan` berisi instruksi tindak lanjut, BUKAN indikasi kegagalan — restore
    tetap dianggap sukses (HTTP 200) meski revisi skema hasil pulihan berbeda dari
    head Alembic aplikasi; endpoint ini SENGAJA tidak menjalankan `alembic upgrade`
    secara otomatis (menumpuk migrasi otomatis di atas aksi yang sudah destruktif
    adalah perusakan kedua tanpa persetujuan admin).
    """

    status: str = Field(description="Status operasi.", examples=["ok"])
    revisi_alembic: str | None = Field(
        default=None,
        description=(
            "Revisi Alembic (`alembic_version.version_num`) yang terbaca dari basis data"
            " setelah restore selesai. `null` bila tabel `alembic_version` tidak ditemukan."
        ),
        examples=["fd3dd550aa99"],
    )
    peringatan: list[str] = Field(
        default_factory=list,
        description=(
            "Peringatan tindak lanjut (mis. skema tidak sinkron dengan head aplikasi)."
            " Daftar kosong berarti tidak ada tindak lanjut yang diperlukan."
        ),
    )
