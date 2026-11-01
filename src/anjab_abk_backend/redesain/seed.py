"""Seed idempoten data redesain (katalog konteks paket v1.3)."""

from __future__ import annotations

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models import RedesainKonteksModel
from .services.konteks_sql import ENTITAS
from .services.riwayat_sql import SqlRiwayatService

# (kode, tema, gelombang, ruang_dugaan, sumber_draft, batas_pemeriksaan)
KONTEKS: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        "K-01",
        "Asesmen dan rapor",
        "G1",
        "Soal terlambat; input nilai; konferensi rapor perlu dipisah",
        "PPT Okt 2026 hlm 4-5",
        "Peluang bukti saat AAS/rapor, BUKAN bukti prioritas redesain",
    ),
    (
        "K-02",
        "Kerusakan sarpras",
        "G1",
        "Laporan WA; antrean; SIM Sarpras",
        "PPT hlm 4,6",
        "Periksa data #73 sementara, alasan penggunaan sistem dan mandat",
    ),
    (
        "K-03",
        "Informasi/keputusan lomba",
        "G1",
        "Serah terima, keputusan dan tenggat",
        "PPT hlm 4,6",
        "Arsip tanggal perlu diperiksa; 3 serah terima bukan otomatis tidak perlu",
    ),
    (
        "K-04",
        "Inventaris dan BOS",
        "G1",
        "Laporan sistem dan dokumen cetak",
        "PPT hlm 4,6",
        "Periksa kewajiban/otoritas laporan sebelum opsi menghapus",
    ),
    (
        "K-05",
        "Kasus murid lintas peran",
        "G2",
        "Alur rujukan dan kerahasiaan",
        "PPT hlm 4",
        "Hindari isi kasus/identitas murid, jalur khusus bila risiko serius",
    ),
    (
        "K-06",
        "Komunikasi orang tua",
        "G2",
        "Saluran dan pengulangan informasi",
        "PPT hlm 4",
        "Komunikasi berganda belum tentu pemborosan",
    ),
    (
        "K-07",
        "Dokumentasi/publikasi",
        "G3",
        "Unggah ganda dan sumber konten",
        "PPT hlm 4",
        "Klarifikasi basis durasi 210 menit dan fungsi akses",
    ),
    (
        "K-08",
        "Remedial dan bimbingan",
        "G2",
        "Variasi kebijakan dan proses",
        "PPT hlm 4",
        "Perbedaan jenjang tidak otomatis masalah",
    ),
    (
        "K-09",
        "Kegiatan menginap dan LPJ",
        "G2",
        "Kegiatan, pelaporan, puncak",
        "PPT hlm 4",
        "Periksa keselamatan, kewajiban serta periode",
    ),
    (
        "K-10",
        "Persiapan awal tahun",
        "G3",
        "Musim kerja, dependensi, jadwal",
        "PPT hlm 4",
        "Periksa kalender per unit, jangan asumsikan sama",
    ),
    (
        "K-11",
        "Rapat dan notulen",
        "G2",
        "Hasil rapat, pengulangan, notulen",
        "PPT hlm 4",
        "Uji rapat episode bersama; satu orang sekali per rapat",
    ),
    (
        "K-12",
        "Proyek lintas mapel",
        "G3 - klarifikasi",
        "Pembagian tanggung jawab",
        "PPT hlm 4",
        "Ketimpangan pembagian belum tentu masalah",
    ),
    (
        "K-13",
        "Kerja sama dan MoU",
        "G3 - klarifikasi",
        "Mandat, persetujuan, evaluasi",
        "PPT hlm 4",
        "Periksa perbedaan formal/aktual dan tenggat",
    ),
    (
        "K-14",
        "Dapodik, ANBK, PIP",
        "G3 - klarifikasi",
        "Sumber dan pembaruan data",
        "PPT hlm 4",
        "Pisahkan subproses; hindari data pribadi murid",
    ),
)
"""14 konteks paket v1.3 (sheet KONTEKS), diurut menurut kode."""


def seed_konteks(session: Session) -> int:
    """Isi katalog konteks 14 baris secara idempoten.

    Kunci `kode`, `INSERT ... ON CONFLICT (kode) DO NOTHING`: baris yang sudah ada
    (termasuk yang telah disunting Tim) tidak ditimpa. Tiap baris yang benar-benar
    baru dicatat riwayatnya dengan `pelaku_kode_orang=NULL` (sistem).

    Args:
        session: Sesi aktif; pemanggil yang commit.

    Returns:
        Jumlah baris yang baru disisipkan pada pemanggilan ini.
    """
    riwayat = SqlRiwayatService(session)
    baru = 0
    for kode, tema, gelombang, ruang, sumber, batas in KONTEKS:
        nilai = {
            "kode": kode,
            "tema": tema,
            "gelombang": gelombang,
            "ruang_dugaan": ruang,
            "sumber_draft": sumber,
            "batas_pemeriksaan": batas,
            "aktif": True,
        }
        stmt = (
            insert(RedesainKonteksModel)
            .values(id=str(uuid.uuid4()), **nilai)
            .on_conflict_do_nothing(index_elements=["kode"])
            .returning(RedesainKonteksModel.id)
        )
        new_id = session.execute(stmt).scalar_one_or_none()
        if new_id is not None:
            riwayat.catat(ENTITAS, new_id, "create", None, nilai, None)
            baru += 1
    return baru
