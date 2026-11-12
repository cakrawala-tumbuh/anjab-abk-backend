"""Skema Pydantic sign-off PI/etik atas protokol riset `TERKUNCI` (`riset_protokol_signoff`).

Satu protokol paling banyak punya satu sign-off. Respons tidak pernah memuat byte berkas;
lampiran PDF diunduh lewat rute terpisah.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

BATAS_PI_NAMA = 200
"""Batas karakter `pi_nama`."""

BATAS_NOMOR_ETIK = 100
"""Batas karakter `nomor_persetujuan_etik`."""

MAGIC_PDF = b"%PDF-"
"""Byte awal yang wajib ada pada berkas PDF yang sah."""


class SignoffRead(BaseModel):
    """Metadata sign-off PI/etik; TIDAK memuat byte lampiran."""

    id: str = Field(description="ID sign-off (UUID v4).")
    protokol_id: str = Field(description="ID protokol riset `TERKUNCI` yang disahkan.")
    pi_nama: str = Field(description="Nama PI sebagaimana dinyatakan pencatat.")
    tanggal_persetujuan_etik: date = Field(description="Tanggal persetujuan etik (<= hari ini).")
    nomor_persetujuan_etik: str | None = Field(description="Nomor surat persetujuan etik.")
    lampiran_nama: str = Field(description="Nama berkas PDF yang diunggah.")
    lampiran_ukuran: int = Field(description="Ukuran PDF dalam byte.")
    lampiran_sha256: str = Field(description="SHA-256 heksadesimal atas byte PDF.")
    dicatat_oleh: str = Field(description="Subjek token pencatat.")
    created_at: datetime
