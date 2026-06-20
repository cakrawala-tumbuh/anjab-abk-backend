#!/bin/sh
# Restore database PostgreSQL dari file dump custom pg_dump.
# DATABASE_URL wajib di-set di environment (format: postgresql+psycopg://user:pass@host:port/db).
# Pakai: ./scripts/restore.sh <dump_file>
#
# PERINGATAN: perintah ini menghapus semua data yang ada sebelum restore.

set -eu

DUMP_FILE="${1:?Pakai: $0 <dump_file>}"

: "${DATABASE_URL:?DATABASE_URL tidak di-set. Set via environment sebelum menjalankan perintah ini.}"

if [ ! -f "$DUMP_FILE" ]; then
    printf 'Error: file tidak ditemukan: %s\n' "$DUMP_FILE" >&2
    exit 1
fi

# Strip prefix driver SQLAlchemy agar kompatibel dengan pg_restore
PG_URL=$(printf '%s' "$DATABASE_URL" \
    | sed 's|postgresql+psycopg://|postgresql://|; s|postgresql+psycopg2://|postgresql://|')

printf 'PERINGATAN: Restore akan menghapus data yang ada. Lanjutkan? [y/N] '
read -r CONFIRM
case "$CONFIRM" in
    y|Y) ;;
    *) printf 'Dibatalkan.\n'; exit 0 ;;
esac

printf 'Restore database dari %s ...\n' "$DUMP_FILE"
pg_restore --format=custom --no-acl --no-owner --clean --if-exists -d "$PG_URL" "$DUMP_FILE"
printf 'Selesai.\n'
