#!/bin/sh
# Backup database PostgreSQL ke format custom pg_dump.
# DATABASE_URL wajib di-set di environment (format: postgresql+psycopg://user:pass@host:port/db).
# Pakai: ./scripts/backup.sh [output_dir]
#
# File output: <output_dir>/backup_<YYYYMMDD_HHMMSS>.dump

set -eu

OUTPUT_DIR="${1:-backups}"
mkdir -p "$OUTPUT_DIR"

: "${DATABASE_URL:?DATABASE_URL tidak di-set. Set via environment sebelum menjalankan perintah ini.}"

# Strip prefix driver SQLAlchemy agar kompatibel dengan pg_dump
PG_URL=$(printf '%s' "$DATABASE_URL" \
    | sed 's|postgresql+psycopg://|postgresql://|; s|postgresql+psycopg2://|postgresql://|')

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DEST="${OUTPUT_DIR}/backup_${TIMESTAMP}.dump"

printf 'Backup database ke %s ...\n' "$DEST"
pg_dump --format=custom --no-acl --no-owner "$PG_URL" > "$DEST"
printf 'Selesai: %s\n' "$DEST"
