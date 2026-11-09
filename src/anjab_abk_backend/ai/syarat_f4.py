"""Gerbang F4 (Kebijakan AI-First, KAI:16) bersama untuk fungsi AI P06 dan P07.

Pada jalur F4, AI baru boleh menulis sesudah klaim dan analisis tervalidasi, data kuantitatif
sah, dan audit bukti minimal. Isi "audit bukti minimal" belum dipastikan Tim Kajian, jadi
modul ini memegang **definisi sementara yang bisa diuji** (versi ``VERSI_SYARAT_F4``) dan dapat
direvisi tanpa mengubah pemanggilnya:

1. Klaim tervalidasi: ``redesain_penilaian.status_bukti`` masalah itu ``"Diperkuat untuk
   klaim"``; tanpa penilaian dianggap belum tervalidasi.
2. Audit bukti minimal: minimal satu ``redesain_bukti`` masalah itu berstatus pemeriksaan
   ``"Diperiksa sesuai klaim"``, dan tidak satu pun ``"Diperselisihkan"``.
3. Data kuantitatif sah: dipenuhi secara struktural oleh pemanggil, bukan diperiksa di sini.
   Tidak ada angka tak terverifikasi yang dikirim ke model (``source_verified_quantities``
   selalu kosong, ``ti_detail.jam_per_minggu`` tidak pernah dirakit), dan skema keluaran
   mewajibkan ``unknown_parameters`` terisi.

Modul ini hanya membaca.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import RedesainBuktiModel, RedesainPenilaianModel

__all__ = [
    "KODE_AUDIT_BUKTI_BELUM_MINIMAL",
    "KODE_BUKTI_DIPERSELISIHKAN",
    "KODE_KLAIM_BELUM_TERVALIDASI",
    "STATUS_BUKTI_TERVALIDASI",
    "STATUS_PEMERIKSAAN_DIPERSELISIHKAN",
    "STATUS_PEMERIKSAAN_SESUAI",
    "VERSI_SYARAT_F4",
    "periksa_syarat_f4",
]

VERSI_SYARAT_F4 = "sementara-2026-11"
"""Versi definisi gerbang F4. Keputusan sementara; ikut tercatat di ``parameter`` run agar usulan
lama tetap bisa ditelusuri ke definisi yang berlaku saat diajukan."""

STATUS_BUKTI_TERVALIDASI = "Diperkuat untuk klaim"
"""Nilai ``redesain_penilaian.status_bukti`` yang dianggap klaim tervalidasi (syarat 1)."""

STATUS_PEMERIKSAAN_SESUAI = "Diperiksa sesuai klaim"
"""Status pemeriksaan bukti yang dihitung sebagai audit (syarat 2)."""

STATUS_PEMERIKSAAN_DIPERSELISIHKAN = "Diperselisihkan"
"""Status pemeriksaan bukti yang menggugurkan gerbang (syarat 2)."""

KODE_KLAIM_BELUM_TERVALIDASI = "KLAIM_BELUM_TERVALIDASI"
"""Penilaian tidak ada atau ``status_bukti`` bukan ``STATUS_BUKTI_TERVALIDASI``."""

KODE_AUDIT_BUKTI_BELUM_MINIMAL = "AUDIT_BUKTI_BELUM_MINIMAL"
"""Belum ada bukti masalah itu yang berstatus ``STATUS_PEMERIKSAAN_SESUAI``."""

KODE_BUKTI_DIPERSELISIHKAN = "BUKTI_DIPERSELISIHKAN"
"""Ada bukti masalah itu yang berstatus ``STATUS_PEMERIKSAAN_DIPERSELISIHKAN``."""


def periksa_syarat_f4(session: Session, masalah_id: str) -> list[str]:
    """Periksa gerbang F4 (definisi ``VERSI_SYARAT_F4``) untuk satu masalah redesain.

    Pemanggil yang memastikan masalahnya ada (404) sebelum memanggil fungsi ini; masalah yang
    tidak ada akan gagal syarat 1 dan 2 karena tak punya penilaian maupun bukti.

    Args:
        session: Sesi basis data.
        masalah_id: Id ``redesain_masalah``.

    Returns:
        Daftar kode syarat yang gagal, urut ``KLAIM_BELUM_TERVALIDASI``,
        ``AUDIT_BUKTI_BELUM_MINIMAL``, ``BUKTI_DIPERSELISIHKAN``; kosong berarti lolos.

    Example:
        >>> periksa_syarat_f4(session, masalah_id)  # doctest: +SKIP
        ['AUDIT_BUKTI_BELUM_MINIMAL']
    """
    gagal: list[str] = []
    status_bukti = session.scalar(
        select(RedesainPenilaianModel.status_bukti).where(
            RedesainPenilaianModel.masalah_id == masalah_id
        )
    )
    if status_bukti != STATUS_BUKTI_TERVALIDASI:
        gagal.append(KODE_KLAIM_BELUM_TERVALIDASI)
    hitung = dict(
        session.execute(
            select(RedesainBuktiModel.status_pemeriksaan, func.count())
            .where(RedesainBuktiModel.masalah_id == masalah_id)
            .group_by(RedesainBuktiModel.status_pemeriksaan)
        ).all()
    )
    if not hitung.get(STATUS_PEMERIKSAAN_SESUAI):
        gagal.append(KODE_AUDIT_BUKTI_BELUM_MINIMAL)
    if hitung.get(STATUS_PEMERIKSAAN_DIPERSELISIHKAN):
        gagal.append(KODE_BUKTI_DIPERSELISIHKAN)
    return gagal
