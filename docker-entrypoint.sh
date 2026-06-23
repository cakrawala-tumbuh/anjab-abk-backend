#!/bin/sh
# Entrypoint container runtime: inisialisasi DB otomatis lalu jalankan aplikasi.
#
# `initdb` idempoten & aman diulang tiap `up -d` (alembic_version mencegah migrasi lama
# dijalankan ulang; seed melompati baris yang sudah ada). Tidak ada langkah deploy manual.
# `exec "$@"` mengganti proses shell dengan CMD (uvicorn) → sinyal (SIGTERM) diteruskan benar.
set -e

python -m anjab_abk_backend.initdb

exec "$@"
