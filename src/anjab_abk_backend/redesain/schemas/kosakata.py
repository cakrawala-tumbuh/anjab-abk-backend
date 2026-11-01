"""Kosakata baku register redesain (nilai pilihan yang dipakai seluruh entitas redesain).

Semua tipe berupa `Literal` Pydantic; kolom DB terkait bertipe `String(40)` tanpa
CHECK constraint (pola `Cabang` di `schemas/common.py`) sehingga penambahan nilai
tidak membutuhkan migrasi. Kosakata khusus satu entitas ditambahkan oleh item
pemiliknya di modul ini juga.
"""

from __future__ import annotations

from typing import Literal

GRUP_TIM_KAJIAN = "tim-kajian"
"""Nama grup Authentik untuk Tim Kajian (pemilik akses data redesain)."""

GRUP_SEKOLAH_PENGISI = "sekolah-pengisi"
"""Nama grup Authentik untuk guru/staf sekolah pengisi keterangan sekolahnya sendiri."""

Gelombang = Literal["G1", "G2", "G3", "G3 - klarifikasi", "Belum dijadwalkan"]
"""Gelombang pelaksanaan validasi."""

StatusAwal = Literal["Hipotesis", "Keterangan kasus", "Diperkuat untuk klaim", "Diperselisihkan"]
"""Status awal sebuah masalah (sheet MASALAH)."""

StatusBukti = Literal[
    "Hipotesis",
    "Keterangan kasus",
    "Diperkuat untuk klaim",
    "Diperselisihkan",
    "Belum cukup",
]
"""Status dengan bukti (sheet PENILAIAN) = `StatusAwal` + `Belum cukup`."""

StatusLangkah = Literal[
    "Hipotesis",
    "Keterangan kasus",
    "Diperkuat untuk klaim",
    "Diperselisihkan",
    "Tidak berlaku",
]
"""Status sebuah langkah alur = `StatusAwal` + `Tidak berlaku`."""

Skala = Literal["Tinggi", "Sedang", "Rendah", "Belum tahu"]
"""Skala ordinal penilaian."""

Indikasi = Literal["Ada indikasi", "Tidak terlihat", "Belum tahu"]
"""Istilah KHUSUS field indikasi risiko (Lembar Konfirmasi bagian E)."""

YaTidak = Literal["Ya", "Tidak", "Belum tahu"]
"""Pilihan untuk field ya/tidak selain indikasi risiko (jangan pakai `Indikasi`)."""

Kesesuaian = Literal["Ya", "Sebagian", "Tidak", "Belum bisa memastikan"]
"""Kesesuaian dugaan Tim dengan keadaan sekolah (Lembar Konfirmasi bagian C)."""

SumberKonfirmasi = Literal["daring", "luring"]
"""Asal isian konfirmasi: diisi sendiri lewat aplikasi (`daring`) atau isian kertas (`luring`)."""

StatusKonfirmasi = Literal["draf", "terkirim"]
"""Status konfirmasi; `terkirim` tidak dapat diubah lagi."""
