#!/bin/sh
# Buat revisi Alembic BARU (satu berkas per perubahan) dari selisih model ↔ schema.
#
# Memakai PostgreSQL ephemeral yang sama dengan harness test: DB dinaikkan, di-`upgrade
# head`, lalu `alembic revision --autogenerate` membandingkan model dengan schema head
# dan menulis berkas revisi baru ke migrations/versions/ di host. DB dibuang setelahnya.
#
# Pakai: make migration m="deskripsi perubahan"   (JANGAN edit revisi lama; buat yang baru)

set -eu

MSG="${1:?Pakai: make migration m=\"deskripsi perubahan\"}"
COMPOSE="docker compose -f docker-compose.test.yml"
export TEST_IMAGE="${TEST_IMAGE:-anjab-abk-backend-test}"

cleanup() { $COMPOSE down -v --remove-orphans >/dev/null 2>&1 || true; }
trap cleanup EXIT

# `compose run` menaikkan service `db` (depends_on healthy) lebih dulu. Berkas revisi
# ditulis lewat bind-mount; --user + HOME=/tmp agar berkas dimiliki user host (bukan root)
# dan ruff post-write hook punya direktori cache yang bisa ditulis.
$COMPOSE run --rm \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e RUFF_CACHE_DIR=/tmp/.ruff_cache \
    -v "$(pwd)/migrations/versions:/app/migrations/versions" \
    test sh -c "alembic upgrade head && alembic revision --autogenerate -m \"$MSG\""

printf '\nRevisi baru ditulis ke migrations/versions/.\n'
printf 'REVIEW berkasnya (sesuaikan bila perlu), lalu `alembic upgrade head` & commit.\n'
