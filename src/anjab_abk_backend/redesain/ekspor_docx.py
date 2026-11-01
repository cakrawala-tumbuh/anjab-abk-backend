"""Pembangkit DOCX untuk Ringkasan Telaah Prioritas Yayasan dan Lembar Konfirmasi pra-isi.

Dokumen dibangun dari kode (tanpa berkas templat biner). Isi ringkasan hanya diambil dari
`RingkasanYayasanRow`, sehingga tidak pernah memuat nama orang maupun isi konfirmasi per orang.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO

from docx import Document
from docx.document import Document as DocumentType

from .schemas.yayasan import RingkasanYayasanRow

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
"""Media type respons unduhan DOCX."""

PILIHAN_INDIKASI = ("Ada indikasi", "Tidak terlihat", "Belum tahu")
"""Tiga pilihan kotak indikasi risiko (istilah Lembar Konfirmasi bagian E)."""

JUDUL_RINGKASAN = "RINGKASAN TELAAH PRIORITAS — YAYASAN"
SUBJUDUL_RINGKASAN = "Prioritas masalah ≠ izin mengubah pekerjaan"
JUDUL_LEMBAR = "LEMBAR KONFIRMASI SEKOLAH"


@dataclass(frozen=True)
class DataLembar:
    """Masukan Lembar Konfirmasi bagian A (diisi Tim sebelum sesi).

    Attributes:
        masalah_kode: Kode masalah (Masalah_ID).
        konteks_kode: Kode konteks (Konteks_ID).
        proses_kode: Kode proses tertaut (Process_ID), terurut.
        sekolah: Nama sekolah atau keterangan sekolah; None bila belum ditetapkan.
        jenjang: Nama jenjang sekolah; None bila tidak diketahui.
        periode_acuan: Periode acuan masalah.
        sumber_awal: Sumber awal dan keterbatasan.
        status_awal: Status awal masalah (bukan status dengan bukti).
        rumusan_hipotesis: Rumusan dugaan.
    """

    masalah_kode: str
    konteks_kode: str
    proses_kode: Sequence[str]
    sekolah: str | None
    jenjang: str | None
    periode_acuan: str
    sumber_awal: str
    status_awal: str
    rumusan_hipotesis: str


def _v(nilai: object) -> str:
    """Tampilkan nilai; None atau string kosong ditulis `—`."""
    if nilai is None or nilai == "":
        return "—"
    return str(nilai)


def _kotak(terpilih: str | None) -> str:
    """Susun kotak indikasi dengan pilihan tercentang `■` dan sisanya `□`."""
    return " ".join(f"{'■' if p == terpilih else '□'} {p}" for p in PILIHAN_INDIKASI)


def _tabel(doc: DocumentType, baris: Sequence[tuple[str, str]]) -> None:
    """Tambah tabel dua kolom label-nilai."""
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    for label, nilai in baris:
        sel = t.add_row().cells
        sel[0].text = label
        sel[1].text = nilai


def _halaman_ringkasan(doc: DocumentType, r: RingkasanYayasanRow) -> None:
    """Tulis satu halaman ringkasan untuk satu masalah."""
    doc.add_heading(JUDUL_RINGKASAN, level=1)
    doc.add_paragraph(SUBJUDUL_RINGKASAN)
    doc.add_heading("Informasi", level=2)
    _tabel(
        doc,
        [
            ("Kode masalah", r.masalah_kode),
            ("Sekolah / periode", f"{_v(r.sekolah_konteks)} / {_v(r.periode_acuan)}"),
            ("Pernyataan masalah", _v(r.rumusan_hipotesis)),
            ("Status bukti", _v(r.status_bukti)),
            ("Diluruskan sekolah", _v(r.diluruskan_sekolah)),
        ],
    )
    doc.add_heading("A. Penilaian Tim", level=2)
    _tabel(
        doc,
        [
            ("K1", _v(r.k1)),
            ("K2", _v(r.k2)),
            ("K3", _v(r.k3)),
            ("K4", _v(r.k4)),
            ("Alasan rentang berbeda", _v(r.alasan_rentang_beda)),
            ("Saran Tim", _v(r.saran_otomatis)),
        ],
    )
    doc.add_paragraph(f"Indikasi risiko: {_kotak(r.indikasi_kritis)}")
    doc.add_heading("B. Keputusan", level=2)
    _tabel(
        doc,
        [
            ("Keputusan", _v(r.prioritas_final)),
            ("Alasan", _v(r.alasan_final)),
            ("Pemutus", _v(r.pemutus)),
            ("Tanggal", _v(r.tanggal_keputusan.isoformat() if r.tanggal_keputusan else None)),
        ],
    )


def _ke_bytes(doc: DocumentType) -> bytes:
    """Serialisasi dokumen ke bytes."""
    buf = BytesIO()
    doc.save(buf)
    return buf.getvalue()


def bangun_ringkasan(rows: Sequence[RingkasanYayasanRow]) -> bytes:
    """Bangun DOCX ringkasan yayasan, satu masalah per halaman (page break antar halaman).

    Args:
        rows: Baris ringkasan, dalam urutan yang diinginkan; minimal satu.

    Returns:
        Isi berkas DOCX.
    """
    doc = Document()
    for i, r in enumerate(rows):
        if i:
            doc.add_page_break()
        _halaman_ringkasan(doc, r)
    return _ke_bytes(doc)


def bangun_lembar_konfirmasi(d: DataLembar) -> bytes:
    """Bangun DOCX Lembar Konfirmasi: bagian A terisi, bagian B-E isian kosong.

    Args:
        d: Data bagian A.

    Returns:
        Isi berkas DOCX.
    """
    doc = Document()
    doc.add_heading(JUDUL_LEMBAR, level=1)
    doc.add_heading("A. Identitas (diisi Tim sebelum sesi)", level=2)
    _tabel(
        doc,
        [
            ("Masalah_ID", d.masalah_kode),
            ("Konteks_ID", d.konteks_kode),
            ("Process_ID", ", ".join(d.proses_kode) or "—"),
            ("Sekolah", _v(d.sekolah)),
            ("Jenjang", _v(d.jenjang)),
            ("Periode", d.periode_acuan),
            ("Sumber awal & keterbatasan", _v(d.sumber_awal)),
            ("Status awal", d.status_awal),
            ("Rumusan dugaan", _v(d.rumusan_hipotesis)),
        ],
    )
    for judul in (
        "B. Cerita sekolah (diisi sekolah)",
        "C. Koreksi atas alur (diisi sekolah)",
        "D. Bukti yang dimiliki (diisi sekolah)",
    ):
        doc.add_heading(judul, level=2)
        doc.add_paragraph("\n\n")
    doc.add_heading("E. Indikasi risiko", level=2)
    doc.add_paragraph(_kotak(None))
    doc.add_paragraph("Keterangan: ")
    return _ke_bytes(doc)
