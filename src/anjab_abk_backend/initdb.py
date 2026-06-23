"""Inisialisasi database saat startup container: migrasi + seed (idempoten).

Dipanggil oleh entrypoint container SEBELUM aplikasi dimulai sehingga **deploy tidak
butuh langkah manual** (`alembic upgrade head` / `seed_db` tidak perlu dijalankan
tangan). **Aman dijalankan berkali-kali** (tiap `docker compose up -d`, restart, atau
re-deploy) karena keduanya idempoten:

- ``alembic upgrade head`` hanya menerapkan revisi yang BELUM tercatat di tabel
  ``alembic_version`` — migrasi lama TIDAK dijalankan ulang. Jadi `up -d` kedua dst.
  praktis no-op (hanya satu query cek versi), bukan eksekusi init berulang.
- ``seed_all`` melompati baris master data yang sudah ada.

Catatan replika: dirancang untuk deployment **satu instance** (1 sesi studi = 1
instance — lihat model deployment proyek). Untuk multi-replica, jalankan modul ini
sebagai **job init terpisah** (sekali, sebelum app naik), BUKAN di tiap replika, agar
tidak ada balapan migrasi.
"""

from __future__ import annotations

import logging
import time

from .db import ping, session_scope
from .migrate import upgrade
from .seed_db import seed_all

logger = logging.getLogger("anjab_abk_backend.initdb")


def _wait_for_db(attempts: int = 30, delay: float = 2.0) -> None:
    """Tunggu database dapat dijangkau (mis. service DB baru naik saat `up -d`)."""
    for i in range(1, attempts + 1):
        try:
            ping()
            return
        except Exception as exc:  # noqa: BLE001 — sengaja menampung semua galat koneksi
            logger.info("menunggu database siap (%d/%d): %s", i, attempts, exc)
            time.sleep(delay)
    raise RuntimeError(f"database tidak siap setelah {attempts} percobaan")


def main() -> None:
    """Jalankan migrasi lalu seed master data; aman diulang setiap startup."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _wait_for_db()
    logger.info("menerapkan migrasi (alembic upgrade head)...")
    upgrade()  # idempoten: hanya revisi yang belum diterapkan
    # Alembic env.py memanggil fileConfig() yang menyetel ulang logging root ke WARNING;
    # kembalikan ke INFO agar progres seed di bawah tetap terlihat di log deploy.
    logging.getLogger().setLevel(logging.INFO)
    logger.info("seeding master data (idempoten)...")
    with session_scope() as session:
        seed_all(session)
    logger.info("inisialisasi database selesai")


if __name__ == "__main__":
    main()
