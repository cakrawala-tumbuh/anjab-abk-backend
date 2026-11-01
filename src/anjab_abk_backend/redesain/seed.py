"""Seed idempoten data redesain (katalog konteks + hipotesis masalah awal paket v1.3)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models import RedesainCakupanJabatanModel, RedesainKonteksModel, RedesainMasalahModel
from .services.cakupan_jabatan_sql import ENTITAS as ENTITAS_CAKUPAN
from .services.konteks_sql import ENTITAS
from .services.masalah_sql import ENTITAS as ENTITAS_MASALAH
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


MASALAH: tuple[tuple[str, str, str, str, str, str, str, str, str], ...] = (
    (
        "M-K01-01",
        "K-01",
        "Belum ditetapkan",
        "TA 2026/27 belum dipastikan",
        "Dugaan keterlambatan soal menghambat penyiapan ujian",
        "PPT hlm 5; staf kurikulum — unit asal harus dicocokkan",
        "Hipotesis",
        "G1",
        "Uji arsip tanggal unggah dan alur konfirmasi",
    ),
    (
        "M-K01-02",
        "K-01",
        "Belum ditetapkan",
        "Belum dipastikan",
        "Dugaan input nilai berulang pada sistem/format berbeda",
        "PPT hlm 5; jejak sistem lokal belum diuji",
        "Hipotesis",
        "G1",
        "Periksa fungsi kedua isian; jangan langsung sebut duplikasi",
    ),
    (
        "M-K01-03",
        "K-01",
        "Sumber contoh TK Semarang",
        "Belum dipastikan",
        "Dugaan konferensi rapor terlalu padat pada satu hari",
        "PPT hlm 5; contoh 15 menit/orang tua, basis & dampak perlu diuji",
        "Hipotesis",
        "G1",
        "Periksa jumlah orang tua, slot dan layanan",
    ),
    (
        "M-K02-01",
        "K-02",
        "Belum ditetapkan",
        "Belum dipastikan",
        "Dugaan status laporan kerusakan sulit ditelusuri",
        "PPT hlm 6; data Sarpras Bandung #73 sementara",
        "Hipotesis",
        "G1",
        "Telusuri pelapor, penerima, SIM serta antrean",
    ),
    (
        "M-K02-02",
        "K-02",
        "Belum ditetapkan",
        "Belum dipastikan",
        "Dugaan SIM Sarpras belum digunakan sesuai kebutuhan",
        "PPT hlm 6; sebab belum diketahui",
        "Hipotesis",
        "G1",
        "Periksa akses, kesiapan, alasan dan aturan",
    ),
    (
        "M-K03-01",
        "K-03",
        "Belum ditetapkan",
        "Belum dipastikan",
        "Dugaan keputusan mengikuti lomba terlambat",
        "PPT hlm 6; >3 hari dan 3 serah terima perlu arsip",
        "Hipotesis",
        "G1",
        "Periksa tanggal, kewajiban dan siapa memutuskan",
    ),
    (
        "M-K04-01",
        "K-04",
        "Belum ditetapkan",
        "Belum dipastikan",
        "Dugaan inventaris digital tetap harus dilaporkan dalam cetak",
        "PPT hlm 6; dasar cetak belum diperiksa",
        "Hipotesis",
        "G1",
        "Periksa kebutuhan pengesahan BOS/asistensi",
    ),
    (
        "M-K05-01",
        "K-05",
        "Belum ditetapkan",
        "Belum dipastikan",
        "Perlu diperiksa kejelasan rujukan kasus murid",
        "PPT hlm 4 dan rencana validasi; tanpa isi kasus pribadi",
        "Hipotesis",
        "G2",
        "Periksa alur netral tanpa membuka data sensitif",
    ),
)
"""Delapan hipotesis awal sheet MASALAH paket v1.3 (`MASALAH!A5:I12`).

Urutan kolom: kode, kode konteks, teks sekolah (→ `keterangan_sekolah`), periode acuan,
rumusan hipotesis, sumber awal & keterbatasan, status awal, gelombang, penjelasan
alternatif. `sekolah_id` selalu NULL ("Belum ditetapkan") sampai Tim menetapkannya.
"""


def seed_masalah(session: Session) -> int:
    """Isi 8 hipotesis masalah awal secara idempoten (dipanggil SESUDAH `seed_konteks`).

    Kunci `kode`, `INSERT ... ON CONFLICT (kode) DO NOTHING`: baris yang sudah ada
    (termasuk suntingan Tim) tidak ditimpa. `konteks_id` diresolusi dari kode konteks;
    baris yang konteksnya tidak ada dilewati. Tiap baris baru dicatat riwayatnya dengan
    `pelaku_kode_orang=NULL` (sistem).

    Args:
        session: Sesi aktif; pemanggil yang commit.

    Returns:
        Jumlah baris yang baru disisipkan pada pemanggilan ini.
    """
    riwayat = SqlRiwayatService(session)
    rows = session.execute(select(RedesainKonteksModel.kode, RedesainKonteksModel.id)).all()
    konteks_ids: dict[str, str] = {r[0]: r[1] for r in rows}
    baru = 0
    for kode, kode_konteks, sekolah, periode, rumusan, sumber, status, gel, alt in MASALAH:
        konteks_id = konteks_ids.get(kode_konteks)
        if konteks_id is None:
            continue
        nilai = {
            "kode": kode,
            "konteks_id": konteks_id,
            "sekolah_id": None,
            "keterangan_sekolah": sekolah,
            "periode_acuan": periode,
            "periode_pasti": False,
            "rumusan_hipotesis": rumusan,
            "sumber_awal_keterbatasan": sumber,
            "status_awal": status,
            "gelombang": gel,
            "penjelasan_alternatif": alt,
            "pic_kode_orang": None,
            "dibuka_untuk_konfirmasi": False,
        }
        stmt = (
            insert(RedesainMasalahModel)
            .values(id=str(uuid.uuid4()), **nilai)
            .on_conflict_do_nothing(index_elements=["kode"])
            .returning(RedesainMasalahModel.id)
        )
        new_id = session.execute(stmt).scalar_one_or_none()
        if new_id is not None:
            riwayat.catat(
                ENTITAS_MASALAH, new_id, "create", None, {**nilai, "uraian_tugas_ids": []}, None
            )
            baru += 1
    return baru


CAKUPAN: tuple[tuple[str, str], ...] = (
    ("J-01", "Kepala Sekolah"),
    ("J-02", "Wakasek Kurikulum"),
    ("J-03", "Staf Wakasek Kurikulum"),
    ("J-04", "Wakasek Kesiswaan"),
    ("J-05", "Staf Wakasek Kesiswaan"),
    ("J-06", "Wakasek Sarpras"),
    ("J-07", "Wakasek Humas"),
    ("J-08", "Koordinator Sarpras"),
    ("J-09", "Koordinator Humas"),
    ("J-10", "Pembina OSIS"),
    ("J-11", "Koordinator Ekstrakurikuler"),
    ("J-12", "Koordinator Pramuka"),
    ("J-13", "Wali Kelas"),
    ("J-14", "Guru Kelas SD"),
    ("J-15", "Guru Kelas TK"),
    ("J-16", "Guru Mapel SMP"),
    ("J-17", "Guru Mapel SMA"),
    ("J-18", "Guru BK"),
    ("J-19", "Operator Dapodik"),
)
"""Sembilan belas jabatan awal sheet CAKUPAN_19 paket v1.3 (`CAKUPAN_19!A5:B23`)."""

CABANG_CAKUPAN: tuple[str, ...] = ("Bandung", "Semarang")
"""Cabang yang masing-masing mendapat satu baris per entri cakupan."""


def seed_cakupan_jabatan(session: Session) -> int:
    """Isi 19 entri cakupan x 2 cabang (38 baris) secara idempoten.

    Kunci (`role_kode`, `cabang`), `INSERT ... ON CONFLICT DO NOTHING`: baris yang sudah
    ada (termasuk suntingan Tim) tidak ditimpa. `jabatan_id` selalu NULL dan semua status
    memakai default; pemetaan ke master jabatan dilakukan manual oleh Tim. Tiap baris baru
    dicatat riwayatnya dengan `pelaku_kode_orang=NULL` (sistem).

    Args:
        session: Sesi aktif; pemanggil yang commit.

    Returns:
        Jumlah baris yang baru disisipkan pada pemanggilan ini.
    """
    riwayat = SqlRiwayatService(session)
    baru = 0
    for role_kode, nama in CAKUPAN:
        for cabang in CABANG_CAKUPAN:
            nilai = {"role_kode": role_kode, "nama_jabatan": nama, "cabang": cabang}
            stmt = (
                insert(RedesainCakupanJabatanModel)
                .values(id=str(uuid.uuid4()), **nilai)
                .on_conflict_do_nothing(constraint="uq_redesain_cakupan_jabatan_role_cabang")
                .returning(RedesainCakupanJabatanModel.id)
            )
            new_id = session.execute(stmt).scalar_one_or_none()
            if new_id is not None:
                riwayat.catat(ENTITAS_CAKUPAN, new_id, "create", None, nilai, None)
                baru += 1
    return baru
