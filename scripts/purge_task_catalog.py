"""Purge master data catalog Task Inventory: TugasPokok, DetilTugas, UraianTugas.

Seeder (`taskinv/seed.py::seed_catalog_models`) bersifat insert-if-absent —
`ConflictError` di-`pass`, tidak pernah menghapus maupun mem-backfill baris lama.
Saat `task_catalog.json` diganti total (bukan ditambah), katalog lama HARUS dipurge
lebih dulu, baru dijalankan `seed_all`/`initdb` lagi — kalau tidak, baris lama & baru
akan campur aduk.

**Jendela aman**: jalankan skrip ini HANYA selama belum ada sesi Task Inventory yang
berjalan. `ti_seleksi`, `ti_tahap2`, `ti_detail` merujuk katalog lewat `task_kode`
(bukan ID) — purge setelah ada sesi akan merusak data transaksi yang sudah tersimpan.
Cek dulu lewat `mcp__anjab-abk__daftar_ti_sesi` (atau `GET /api/v1/task-inventory/sesi`)
bahwa totalnya nol.

Urutan hapus: `ti_uraian_tugas` dulu (tidak punya FK ke tugas_pokok/detil_tugas — bukan
constraint yang menegakkan urutan, tapi baris uraian yang menunjuk ID yang segera hilang
sebaiknya tidak dibiarkan menggantung walau sesaat), lalu `ti_tugas_pokok` dan
`ti_detil_tugas` (baris link M2M `ti_tugas_pokok_jabatan`/`ti_detil_tugas_jabatan` ikut
terhapus otomatis lewat `ON DELETE CASCADE`). Tabel `jabatan` TIDAK disentuh — jabatan
tetap ada meski dibuat otomatis dari `kategori_jabatan` katalog lama, karena bisa saja
sudah dipakai partisipan/sesi/instrumen lain di luar Task Inventory.

Pakai:
    DATABASE_URL=postgresql+psycopg://... python scripts/purge_task_catalog.py
    DATABASE_URL=... python scripts/purge_task_catalog.py --yes   # tanpa konfirmasi interaktif
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from anjab_abk_backend.db import session_scope  # noqa: E402
from anjab_abk_backend.models import (  # noqa: E402
    TiDetilTugasModel,
    TiTugasPokokModel,
    TiUraianTugasModel,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Lewati konfirmasi interaktif (mis. dipakai di CI/skrip).",
    )
    args = parser.parse_args()

    with session_scope() as session:
        n_ut = session.query(TiUraianTugasModel).count()
        n_dt = session.query(TiDetilTugasModel).count()
        n_tp = session.query(TiTugasPokokModel).count()

    print("Katalog Task Inventory saat ini:")
    print(f"  UraianTugas  : {n_ut}")
    print(f"  DetilTugas   : {n_dt}")
    print(f"  TugasPokok   : {n_tp}")

    if n_ut == 0 and n_dt == 0 and n_tp == 0:
        print("Katalog sudah kosong — tidak ada yang perlu dipurge.")
        return

    if not args.yes:
        jawab = input(
            "PERINGATAN: ini menghapus SELURUH katalog Task Inventory di atas "
            "(bukan sesi/jawaban responden). Lanjutkan? [y/N] "
        )
        if jawab.strip().lower() != "y":
            print("Dibatalkan.")
            return

    with session_scope() as session:
        deleted_ut = session.query(TiUraianTugasModel).delete()
        deleted_dt = session.query(TiDetilTugasModel).delete()
        deleted_tp = session.query(TiTugasPokokModel).delete()

    print(
        f"Selesai: {deleted_ut} UraianTugas, {deleted_dt} DetilTugas, "
        f"{deleted_tp} TugasPokok dihapus (baris link M2M ikut terhapus via CASCADE)."
    )
    print("Jalankan seed_all/initdb untuk mengisi ulang dari task_catalog.json terbaru.")


if __name__ == "__main__":
    main()
