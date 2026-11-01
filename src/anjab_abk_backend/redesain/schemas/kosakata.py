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

JenisBukti = Literal[
    "SK/aturan",
    "Keterangan pemegang",
    "Pihak serah terima",
    "Jadwal",
    "Jejak sistem",
    "Keluaran/dokumen",
    "Lainnya",
]
"""Jenis sumber sebuah bukti (sheet BUKTI)."""

StatusPemeriksaanBukti = Literal[
    "Belum diperiksa",
    "Diperiksa terbatas",
    "Diperiksa sesuai klaim",
    "Diperselisihkan",
]
"""Status pemeriksaan sebuah bukti (istilah "Diperiksa sesuai klaim" dipertahankan apa adanya)."""

PrioritasFinal = Literal[
    "P0 - Eskalasi", "K - Klarifikasi", "P1 - Utama", "P2 - Berikutnya", "P3 - Pantau", "Ditunda"
]
"""Prioritas final keputusan Tim Kajian (sheet PENILAIAN); boleh beda dari saran otomatis."""

StatusPenilaian = Literal[
    "Belum ditelaah",
    "Perlu klarifikasi",
    "Siap untuk telaah yayasan",
    "Telah diputuskan",
    "Ditunda",
]
"""Status alur sebuah penilaian; `Telah diputuskan` hanya diset aksi putuskan."""

StatusPenilaianManual = Literal[
    "Belum ditelaah", "Perlu klarifikasi", "Siap untuk telaah yayasan", "Ditunda"
]
"""Status yang boleh diset langsung lewat aksi status (tanpa `Telah diputuskan`)."""

OpsiAlternatif = Literal[
    "Pertahankan",
    "Sederhanakan",
    "Hilangkan pengulangan terbukti",
    "Perjelas kewenangan",
    "Perbaiki alat/dukungan",
    "Uji terbatas",
    "Alihkan tugas bersyarat",
]
"""Opsi alternatif redesain (sheet ALTERNATIF); BUKAN bagian dari skor K1-K4."""

StatusTelaahAlternatif = Literal[
    "Belum ditelaah",
    "Siap telaah",
    "Bersyarat",
    "Tunda gap material",
    "Ditolak",
    "Uji disetujui terpisah",
]
"""Status telaah alternatif; hanya berubah lewat payload eksplisit Tim (bukan dari prioritas)."""

JenisKegiatanSesi = Literal[
    "Klarifikasi",
    "Serah terima",
    "Telaah sumber",
    "Pemeriksaan pimpinan",
    "Forum bersama",
    "Telaah yayasan",
    "Lainnya",
]
"""Jenis kegiatan sebuah sesi partisipasi (sheet SESI)."""

StatusIzinSesi = Literal[
    "Belum ditetapkan",
    "Sudah sesuai izin",
    "Perlu peninjauan izin",
    "Tidak diotorisasi",
]
"""Status izin kegiatan & waktu sebuah sesi; HANYA informasi, tidak pernah memblokir."""
