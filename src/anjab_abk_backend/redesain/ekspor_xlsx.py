"""Pembangkit XLSX register terintegrasi redesain (14 sheet, susunan workbook paket v1.3).

Workbook hanya memuat nilai (tanpa rumus) dari aplikasi dan hanya kode orang; tidak pernah nama
atau email partisipan. Pembangkit murni: seluruh data masuk lewat `DataRegister`, tanpa akses DB.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.worksheet.worksheet import Worksheet

from .schemas.alternatif import AlternatifRead
from .schemas.bukti import BuktiRead
from .schemas.cakupan_jabatan import CakupanJabatanRead
from .schemas.konfirmasi import KonfirmasiDaftarRead
from .schemas.konteks import KonteksRead
from .schemas.koreksi import KoreksiRead
from .schemas.masalah import MasalahRead
from .schemas.penilaian import PenilaianRead
from .schemas.proses import ProsesRead
from .schemas.sesi import SesiRead
from .schemas.versi_metode import VersiMetodeRead
from .schemas.yayasan import RingkasanYayasanRow

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
"""Media type respons unduhan XLSX."""

BARIS_HEADER = 4
"""Baris header sheet data; data mulai di baris berikutnya."""

KALIMAT_STATIS = "Lihat paket metode v1.3; sheet ini tidak dibangkitkan aplikasi."
"""Isi sheet statis (MULAI, RUBRIK, UJI_RUMUS)."""

PENANDA_DIGANTIKAN = "[digantikan]"
"""Awalan kolom catatan paparan/independensi untuk konfirmasi versi lama."""

SHEET: dict[str, tuple[str, list[str]]] = {
    "MULAI": ("YPII | PAKET PRIORITAS & VALIDASI REDESAIN v1.3", []),
    "KONTEKS": (
        "KATALOG KONTEKS | BELUM MENJADI TEMUAN",
        [
            "Konteks_ID",
            "Tema",
            "Gelombang validasi usulan",
            "Ruang dugaan / variasi",
            "Sumber draft",
            "Apa yang perlu diperiksa / batas",
        ],
    ),
    "MASALAH": (
        "KANDIDAT MASALAH LOKAL | DITULIS TIM",
        [
            "Masalah_ID",
            "Konteks_ID",
            "Sekolah / jenjang / cabang",
            "Periode acuan",
            "Rumusan hipotesis (bukan kesimpulan)",
            "Sumber awal & keterbatasan",
            "Status asal",
            "Gelombang validasi usulan",
            "Pemeriksaan/penjelasan alternatif",
            "Process_ID terkait",
            "Task_ID terkait",
            "PIC tim",
        ],
    ),
    "KONFIRMASI": (
        "KETERANGAN SEKOLAH | JAWABAN ASAL DIPERTAHANKAN",
        [
            "Konfirmasi_ID",
            "Masalah_ID",
            "Sekolah / periode",
            "Peran pemberi keterangan (tanpa nama sensitif)",
            "Tanggal sesi",
            "Cerita SEBELUM dugaan ditampilkan",
            "Dugaan baru diperlihatkan?",
            "Kesesuaian setelah ditampilkan",
            "Koreksi / pengecualian (kata asal)",
            "Masalah baru yang disebut",
            "K1 lokal",
            "K2 lokal",
            "K3 lokal",
            "K4 lokal",
            "Alasan/contoh untuk nilai",
            "Indikasi risiko kritis?",
            "Catatan paparan/independensi",
            "Catatan fasilitator & akses",
        ],
    ),
    "BUKTI": (
        "KATALOG BUKTI & SUMBER | TIDAK MENYAMAKAN JENIS KLAIM",
        [
            "Bukti_ID",
            "Masalah_ID",
            "Langkah/Process_ID",
            "Unit dan periode bukti",
            "Jenis bukti",
            "Dibuat/diisi oleh siapa",
            "Sumber independen dari pernyataan awal?",
            "Klaim yang DIDUKUNG",
            "Klaim yang TIDAK DIDUKUNG",
            "Tanggal/versi lokasi",
            "Status pemeriksaan",
            "Pemeriksa & alasan",
            "Catatan privasi/gap",
        ],
    ),
    "ALUR": (
        "PETA ALUR AKTUAL / HIPOTESIS | B1 v7.5",
        [
            "Process_ID",
            "Masalah_ID",
            "Step_ID",
            "Sekolah / jenjang / periode",
            "Tahap proses",
            "Pemicu / input",
            "Pelaksana",
            "Apa yang dikerjakan / sistem",
            "Keluaran & penerima berikutnya",
            "Pemeriksa/pemutus",
            "Hambatan yang diduga/terlihat",
            "Status langkah",
            "Bukti_ID",
            "Koreksi / pihak pemeriksa",
        ],
    ),
    "PENILAIAN": (
        "REKONSILIASI & PRIORITAS | SATU SUMBER PUTUSAN",
        [
            "Masalah_ID (link)",
            "Status bukti untuk klaim",
            "Gap material?",
            "Indikasi kritis?",
            "K1 Akibat layanan",
            "K2 Urgensi/tenggat",
            "K3 Pihak terdampak",
            "K4 Gangguan kerja",
            "Alasan/rentang bukti, beda pendapat",
            "SARAN otomatis",
            "PRIORITAS FINAL pemutus",
            "Alasan final / beda dari saran",
            "Pemeriksa sekolah & konteks",
            "Pemutus berwenang",
            "Tanggal keputusan",
            "Tindak lanjut, PIC, pemicu telaah",
            "Status penilaian",
            "Catatan sumber/versi",
        ],
    ),
    "ALTERNATIF": (
        "PILIHAN REDESAIN | BUKAN BAGIAN DARI SKOR K1–K4",
        [
            "Usulan_ID",
            "Masalah_ID",
            "Opsi tindakan",
            "Alur saat ini vs usulan",
            "Pihak asal",
            "Pihak penerima (jika ada)",
            "Komitmen penerima lintas peran",
            "Jadwal/puncak/tenggat",
            "Keterampilan/akses/kewenangan",
            "Tambahan bersih dan basis waktu (jika diperlukan)",
            "Risiko layanan dan kontinuitas",
            "Gap material penerima?",
            "Status telaah",
            "Pemutus dan keputusan",
            "Prasyarat/monitoring/uji",
            "Catatan versi/bukti",
        ],
    ),
    "SESI": (
        "RENCANA & BEBAN PARTISIPASI | ORANG UNIK × KEGIATAN",
        [
            "Sesi_ID",
            "Orang_kode unik",
            "Unit / jenjang",
            "Peran/fungsi saat sesi",
            "Masalah_ID yang dibahas (bisa lebih dari satu)",
            "Jenis kegiatan",
            "Waktu rencana (menit)",
            "Waktu disepakati (menit)",
            "Waktu kalender nyata jika tersedia",
            "Catatan aktif/jeda/bantuan jika layak",
            "Izin kegiatan & versi",
            "Pemeriksa/PIC",
            "Pekerjaan tersisa / tindak lanjut",
        ],
    ),
    "YAYASAN": (
        "RINGKASAN YAYASAN | TAMPILAN BACA TERHUBUNG",
        [
            "Masalah_ID",
            "Konteks_ID",
            "Sekolah/konteks",
            "Masalah spesifik (hipotesis/teruji)",
            "Sumber & batas awal",
            "Status bukti",
            "K1",
            "K2",
            "K3",
            "K4",
            "Indikasi kritis",
            "Saran tim",
            "Keputusan prioritas",
            "Alasan / perbedaan",
            "Pemutus",
            "Tindak lanjut",
        ],
    ),
    "RUBRIK": ("RUBRIK SEKOLAH | BAHASA SEDERHANA & CONTOH", []),
    "UJI_RUMUS": ("UJI TRIAGE | DATA SINTETIS (BUKAN DATA YPII)", []),
    "CAKUPAN_19": (
        "KENDALI CAKUPAN 19 JABATAN | TERPISAH DARI KATALOG REDESAIN",
        [
            "Role_ID",
            "Jabatan",
            "Bandung (status per unit)",
            "Semarang (status per unit)",
            "Pemegang aktif sudah diperiksa?",
            "Inventori relevan ditinjau?",
            "Peta diperkuat untuk klaim?",
            "Gap/variasi lokal",
            "PIC tindak lanjut",
        ],
    ),
    "PERUBAHAN": (
        "KENDALI VERSI & KEPUTUSAN METODE",
        [
            "Versi",
            "Tanggal",
            "Bagian",
            "Apa yang diperbarui",
            "Alasan / risiko yang dikendalikan",
            "Status dan hasil uji",
            "Pemeriksa/pemutus",
        ],
    ),
}
"""Nama sheet (urut workbook v1.3) -> (judul baris 1, header baris 4). Header kosong = statis."""


@dataclass
class DataRegister:
    """Masukan pembangkit register: seluruh entitas redesain dalam bentuk read-model.

    Attributes:
        konteks: Semua konteks.
        masalah: Semua masalah.
        proses: Semua proses beserta langkahnya.
        konfirmasi: Semua konfirmasi (draf disaring pembangkit; hanya `terkirim` diekspor).
        koreksi: Koreksi per `langkah_id`, terurut waktu.
        bukti: Semua bukti.
        penilaian: Semua penilaian.
        alternatif: Semua alternatif.
        sesi: Semua baris sesi (orang x sesi).
        cakupan: Semua baris cakupan jabatan.
        versi_metode: Semua catatan versi metode.
        yayasan: Baris read-model ringkasan yayasan.
        sekolah: Peta `sekolah_id` -> nama sekolah.
        jabatan: Peta `jabatan_id` -> nama jabatan.
        uraian_kode: Peta `uraian_tugas_id` -> kode-kode link uraian tugas.
    """

    konteks: Sequence[KonteksRead] = ()
    masalah: Sequence[MasalahRead] = ()
    proses: Sequence[ProsesRead] = ()
    konfirmasi: Sequence[KonfirmasiDaftarRead] = ()
    koreksi: Mapping[str, Sequence[KoreksiRead]] = field(default_factory=dict)
    bukti: Sequence[BuktiRead] = ()
    penilaian: Sequence[PenilaianRead] = ()
    alternatif: Sequence[AlternatifRead] = ()
    sesi: Sequence[SesiRead] = ()
    cakupan: Sequence[CakupanJabatanRead] = ()
    versi_metode: Sequence[VersiMetodeRead] = ()
    yayasan: Sequence[RingkasanYayasanRow] = ()
    sekolah: Mapping[str, str] = field(default_factory=dict)
    jabatan: Mapping[str, str] = field(default_factory=dict)
    uraian_kode: Mapping[str, Sequence[str]] = field(default_factory=dict)


def _sel(nilai: object) -> object:
    """Normalkan nilai sel: kosong -> None; tanggal -> ISO; lainnya apa adanya."""
    if nilai is None or nilai == "":
        return None
    if isinstance(nilai, date):
        return nilai.isoformat()
    return nilai


def _gabung(bagian: Sequence[str | None], pemisah: str = ", ") -> str | None:
    """Gabung bagian tak kosong; semuanya kosong -> None."""
    isi = [b for b in bagian if b]
    return pemisah.join(isi) if isi else None


def _dengan(kode: str | None, teks: str | None) -> str | None:
    """Susun `kode: teks`; tanpa teks hanya kode; keduanya kosong -> None."""
    if kode and teks:
        return f"{kode}: {teks}"
    return kode or teks or None


def _baris_konteks(d: DataRegister) -> list[list[object]]:
    """Baris sheet KONTEKS."""
    return [
        [k.kode, k.tema, k.gelombang, k.ruang_dugaan, k.sumber_draft, k.batas_pemeriksaan]
        for k in sorted(d.konteks, key=lambda x: x.kode)
    ]


def _baris_masalah(d: DataRegister) -> list[list[object]]:
    """Baris sheet MASALAH (kolom C dari read-model yayasan, J dari proses, K dari uraian)."""
    kon = {k.id: k.kode for k in d.konteks}
    sek = {y.masalah_id: y.sekolah_konteks for y in d.yayasan}
    prs: dict[str, list[str]] = {}
    for p in d.proses:
        prs.setdefault(p.masalah_id, []).append(p.kode)
    baris: list[list[object]] = []
    for m in sorted(d.masalah, key=lambda x: x.kode):
        tugas = sorted({c for u in m.uraian_tugas_ids for c in d.uraian_kode.get(u, ())})
        baris.append(
            [
                m.kode,
                kon.get(m.konteks_id),
                sek.get(m.id) or (d.sekolah.get(m.sekolah_id) if m.sekolah_id else None),
                m.periode_acuan,
                m.rumusan_hipotesis,
                m.sumber_awal_keterbatasan,
                m.status_awal,
                m.gelombang,
                m.penjelasan_alternatif,
                _gabung(sorted(prs.get(m.id, []))),
                _gabung(tugas),
                m.pic_kode_orang,
            ]
        )
    return baris


def _baris_konfirmasi(d: DataRegister) -> list[list[object]]:
    """Baris sheet KONFIRMASI: hanya `terkirim`, versi lama ditandai `[digantikan]`."""
    mas = {m.id: m for m in d.masalah}
    baris: list[list[object]] = []
    terkirim = [k for k in d.konfirmasi if k.status == "terkirim"]
    kode_masalah = {m.id: m.kode for m in d.masalah}
    terkirim.sort(key=lambda k: (k.created_at, k.id))  # urut buat -> nomor KF stabil saat append
    for n, k in enumerate(terkirim, start=1):
        m = mas.get(k.masalah_id)
        sekolah = _gabung([d.sekolah.get(k.sekolah_id), m.periode_acuan if m else None], " / ")
        catatan = k.catatan_independensi
        if k.digantikan:
            catatan = _gabung([PENANDA_DIGANTIKAN, catatan], " ")
        baris.append(
            [
                f"KF-{n:04d}",
                kode_masalah.get(k.masalah_id),
                sekolah,
                k.peran,
                k.tanggal,
                k.cerita_sebelum,
                k.dugaan_diperlihatkan,
                k.kesesuaian,
                k.koreksi,
                k.masalah_baru,
                k.k1,
                k.k2,
                k.k3,
                k.k4,
                k.alasan_k,
                k.indikasi_risiko,
                catatan,
                k.catatan_akses,
            ]
        )
    return baris


def _baris_bukti(d: DataRegister) -> list[list[object]]:
    """Baris sheet BUKTI."""
    mas = {m.id: m.kode for m in d.masalah}
    lng = {la.id: la.kode for p in d.proses for la in p.langkah}
    baris: list[list[object]] = []
    for b in sorted(d.bukti, key=lambda x: x.kode):
        baris.append(
            [
                b.kode,
                mas.get(b.masalah_id),
                lng.get(b.langkah_id) if b.langkah_id else None,
                b.unit_periode,
                b.jenis,
                _gabung([b.pembuat_kode_orang, b.pembuat_peran], " — "),
                b.independen,
                b.klaim_didukung,
                b.klaim_tidak_didukung,
                b.tanggal_versi_lokasi,
                b.status_pemeriksaan,
                _dengan(b.pemeriksa_kode_orang, b.alasan),
                b.catatan_privasi_gap,
            ]
        )
    return baris


def _baris_alur(d: DataRegister) -> list[list[object]]:
    """Baris sheet ALUR: satu baris per langkah."""
    mas = {m.id: m.kode for m in d.masalah}
    bukti_per_langkah: dict[str, list[str]] = {}
    for b in d.bukti:
        if b.langkah_id:
            bukti_per_langkah.setdefault(b.langkah_id, []).append(b.kode)
    baris: list[list[object]] = []
    for p in sorted(d.proses, key=lambda x: x.kode):
        for la in sorted(p.langkah, key=lambda x: (x.urutan, x.kode)):
            kor = [_dengan(c.kode_orang, c.isi) for c in d.koreksi.get(la.id, ())]
            baris.append(
                [
                    p.kode,
                    mas.get(p.masalah_id),
                    la.kode,
                    _gabung([d.sekolah.get(p.sekolah_id), p.periode], " / "),
                    la.tahap,
                    la.pemicu_input,
                    la.pelaksana,
                    la.pekerjaan_sistem,
                    la.keluaran_penerima,
                    la.pemeriksa_pemutus,
                    la.hambatan,
                    la.status_langkah,
                    _gabung(sorted(bukti_per_langkah.get(la.id, []))),
                    _gabung(kor, "\n"),
                ]
            )
    return baris


def _baris_penilaian(d: DataRegister) -> list[list[object]]:
    """Baris sheet PENILAIAN."""
    mas = {m.id: m.kode for m in d.masalah}
    baris: list[list[object]] = []
    for p in sorted(d.penilaian, key=lambda x: mas.get(x.masalah_id, "")):
        baris.append(
            [
                mas.get(p.masalah_id),
                p.status_bukti,
                p.gap_material,
                p.indikasi_kritis,
                p.k1,
                p.k2,
                p.k3,
                p.k4,
                p.alasan_rentang_beda,
                p.saran_otomatis,
                p.prioritas_final,
                p.alasan_final,
                p.pemeriksa_sekolah_konteks,
                _gabung([p.pemutus_kode_orang, p.pemutus_jabatan], " — "),
                p.tanggal_keputusan,
                p.tindak_lanjut,
                p.status_penilaian,
                p.catatan_sumber_versi,
            ]
        )
    return baris


def _baris_alternatif(d: DataRegister) -> list[list[object]]:
    """Baris sheet ALTERNATIF."""
    mas = {m.id: m.kode for m in d.masalah}
    baris: list[list[object]] = []
    for a in sorted(d.alternatif, key=lambda x: x.kode):
        baris.append(
            [
                a.kode,
                mas.get(a.masalah_id),
                a.opsi,
                a.alur_kini_vs_usulan,
                d.jabatan.get(a.pihak_asal_jabatan_id) if a.pihak_asal_jabatan_id else None,
                d.jabatan.get(a.pihak_penerima_jabatan_id) if a.pihak_penerima_jabatan_id else None,
                a.komitmen_penerima,
                a.jadwal_puncak,
                a.keterampilan_akses,
                a.tambahan_bersih,
                a.risiko_layanan,
                a.gap_penerima,
                a.status_telaah,
                _dengan(a.pemutus_kode_orang, a.keputusan),
                a.prasyarat_monitoring,
                a.catatan_versi_bukti,
            ]
        )
    return baris


def _baris_sesi(d: DataRegister) -> list[list[object]]:
    """Baris sheet SESI: satu baris per orang x sesi."""
    mas = {m.id: m.kode for m in d.masalah}
    baris: list[list[object]] = []
    for s in sorted(d.sesi, key=lambda x: (x.kode_sesi, x.kode_orang)):
        baris.append(
            [
                s.kode_sesi,
                s.kode_orang,
                d.sekolah.get(s.sekolah_id) if s.sekolah_id else None,
                s.peran,
                _gabung(sorted(mas[i] for i in s.masalah_ids if i in mas)),
                s.jenis_kegiatan,
                s.menit_rencana,
                s.menit_disepakati,
                s.waktu_kalender,
                s.catatan,
                _gabung([s.status_izin, s.versi_izin], " "),
                s.pic_kode_orang,
                s.tindak_lanjut,
            ]
        )
    return baris


def _baris_yayasan(d: DataRegister) -> list[list[object]]:
    """Baris sheet YAYASAN."""
    return [
        [
            y.masalah_kode,
            y.konteks_kode,
            y.sekolah_konteks,
            y.rumusan_hipotesis,
            y.sumber_awal_keterbatasan,
            y.status_bukti,
            y.k1,
            y.k2,
            y.k3,
            y.k4,
            y.indikasi_kritis,
            y.saran_otomatis,
            y.prioritas_final,
            y.alasan_final,
            y.pemutus,
            y.tindak_lanjut,
        ]
        for y in sorted(d.yayasan, key=lambda x: x.masalah_kode)
    ]


def _baris_cakupan(d: DataRegister) -> list[list[object]]:
    """Baris sheet CAKUPAN_19: satu baris per `role_kode`, kolom C/D dari cabang."""
    per_role: dict[str, dict[str, CakupanJabatanRead]] = {}
    for c in d.cakupan:
        per_role.setdefault(c.role_kode, {})[c.cabang] = c
    baris: list[list[object]] = []
    for role in sorted(per_role):
        cab = per_role[role]
        acuan = cab.get("Bandung") or cab.get("Semarang")
        assert acuan is not None
        baris.append(
            [
                role,
                acuan.nama_jabatan,
                cab["Bandung"].status_unit if "Bandung" in cab else None,
                cab["Semarang"].status_unit if "Semarang" in cab else None,
                acuan.pemegang_diperiksa,
                acuan.inventori_ditinjau,
                acuan.peta_diperkuat,
                _gabung([c.gap_variasi for c in cab.values()], "\n"),
                _gabung([c.pic_kode_orang for c in cab.values()]),
            ]
        )
    return baris


def _baris_perubahan(d: DataRegister) -> list[list[object]]:
    """Baris sheet PERUBAHAN."""
    return [
        [
            v.versi,
            v.tanggal,
            v.bagian,
            v.apa_diperbarui,
            v.alasan_risiko,
            v.status_hasil_uji,
            v.pemeriksa_pemutus,
        ]
        for v in sorted(d.versi_metode, key=lambda x: (x.versi, x.tanggal, x.bagian))
    ]


_BARIS = {
    "KONTEKS": _baris_konteks,
    "MASALAH": _baris_masalah,
    "KONFIRMASI": _baris_konfirmasi,
    "BUKTI": _baris_bukti,
    "ALUR": _baris_alur,
    "PENILAIAN": _baris_penilaian,
    "ALTERNATIF": _baris_alternatif,
    "SESI": _baris_sesi,
    "YAYASAN": _baris_yayasan,
    "CAKUPAN_19": _baris_cakupan,
    "PERUBAHAN": _baris_perubahan,
}


def _tulis(ws: Worksheet, judul: str, header: list[str], baris: list[list[object]]) -> None:
    """Tulis satu sheet: judul baris 1, header tebal baris 4, data mulai baris 5."""
    ws.cell(row=1, column=1, value=judul).font = Font(bold=True)
    if not header:
        ws.cell(row=2, column=1, value=KALIMAT_STATIS)
        return
    for c, teks in enumerate(header, start=1):
        ws.cell(row=BARIS_HEADER, column=c, value=teks).font = Font(bold=True)
    for r, isi in enumerate(baris, start=BARIS_HEADER + 1):
        for c, nilai in enumerate(isi, start=1):
            ws.cell(row=r, column=c, value=_sel(nilai))


def bangun_register(data: DataRegister) -> bytes:
    """Bangun workbook register 14 sheet dari data redesain.

    Args:
        data: Seluruh entitas redesain yang sudah dibaca lewat seam service.

    Returns:
        Isi berkas XLSX (nilai saja; tanpa rumus). Sheet MULAI/RUBRIK/UJI_RUMUS statis.
    """
    wb = Workbook()
    wb.remove(wb.active)
    for nama, (judul, header) in SHEET.items():
        ws = wb.create_sheet(nama)
        fn = _BARIS.get(nama)
        _tulis(ws, judul, header, fn(data) if fn else [])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
