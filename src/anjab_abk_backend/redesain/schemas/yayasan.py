"""Skema read-model ringkasan yayasan (sheet YAYASAN): turunan masalah + penilaian, bukan tabel."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from .kosakata import StatusBukti
from .penilaian import Peringatan


class RingkasanYayasanRow(BaseModel):
    """Satu baris ringkasan yayasan per masalah, dihitung langsung dari masalah + penilaian.

    Tidak memuat isi konfirmasi per orang maupun nama orang; `pemutus` hanya kode orang
    dan jabatan. Seluruh field penilaian bernilai `null` bila masalah belum dinilai
    (tidak pernah diubah jadi `0`/`"Tidak"`/`"Rendah"`).
    """

    masalah_id: str = Field(description="ID masalah (UUID v4).")
    masalah_kode: str = Field(description="Kode masalah (YAYASAN!A).", examples=["M-K01-01"])
    konteks_kode: str = Field(description="Kode konteks (YAYASAN!B).", examples=["K-01"])
    sekolah_konteks: str | None = Field(
        description="Nama sekolah bila ditetapkan, selain itu `keterangan_sekolah` (YAYASAN!C)."
    )
    periode_acuan: str = Field(description="Periode acuan masalah.")
    rumusan_hipotesis: str = Field(description="Rumusan hipotesis (YAYASAN!D).")
    sumber_awal_keterbatasan: str = Field(description="Sumber awal & keterbatasan (YAYASAN!E).")
    status_bukti: StatusBukti | None = Field(
        description="Status dengan bukti penilaian (YAYASAN!F); null = belum dinilai."
    )
    k1: str | None = Field(description="Skala K1 (YAYASAN!G).")
    k2: str | None = Field(description="Skala K2 (YAYASAN!H).")
    k3: str | None = Field(description="Skala K3 (YAYASAN!I).")
    k4: str | None = Field(description="Skala K4 (YAYASAN!J).")
    indikasi_kritis: str | None = Field(description="Indikasi risiko kritis (YAYASAN!K).")
    saran_otomatis: str | None = Field(description="Saran triase otomatis (YAYASAN!L).")
    prioritas_final: str | None = Field(description="Prioritas final (YAYASAN!M).")
    alasan_final: str | None = Field(description="Alasan keputusan (YAYASAN!N).")
    pemutus: str | None = Field(
        description="`<kode orang> — <jabatan>` pemutus (YAYASAN!O); tidak pernah nama.",
        examples=["O-0001 — Ketua Tim Kajian"],
    )
    tindak_lanjut: str | None = Field(description="Tindak lanjut (YAYASAN!P).")
    proses_kode: list[str] = Field(description="Kode proses tertaut masalah, terurut.")
    status_penilaian: str | None = Field(description="Status penilaian; null = belum dinilai.")
    tanggal_keputusan: date | None = Field(description="Tanggal keputusan; null = belum.")
    diluruskan_sekolah: str | None = Field(description="Catatan diluruskan sekolah.")
    alasan_rentang_beda: str | None = Field(description="Alasan rentang K berbeda.")
    peringatan: list[Peringatan] = Field(
        description="Peringatan hitungan atas prioritas final (aturan BE-8b); kosong bila tak ada."
    )
