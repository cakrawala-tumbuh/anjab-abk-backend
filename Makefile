################################################################################
# Makefile — Automated Test (anjab-abk-backend, Python/FastAPI)
#
# Prinsip:
#  - SEMUA test (lint + unit) berjalan DI DALAM Docker.
#  - Perintah yang sama (`make test`) dipakai di LOKAL maupun di GitHub Actions
#    → tidak mungkin ada perbedaan antara lokal dan CI.
#  - Source di-COPY ke image (bukan bind-mount), sehingga TIDAK ADA artefak test
#    (coverage, __pycache__, .pytest_cache, dll) yang tertulis ke folder project.
################################################################################

IMAGE_NAME ?= $(shell basename $(CURDIR))-test
DOCKERFILE ?= Dockerfile.test
DOCKER_RUN  = docker run --rm $(IMAGE_NAME)
COMPOSE_TEST = docker compose -f docker-compose.test.yml

.DEFAULT_GOAL := test
.PHONY: build lint unit test clean shell help \
        migration backup restore backup-list test-arm64

## help: tampilkan daftar target
help:
	@grep -E '^## ' $(MAKEFILE_LIST) | sed -e 's/## //'

## build: bangun image test (deps + tooling + source)
build:
	docker build -f $(DOCKERFILE) -t $(IMAGE_NAME) .

## lint: jalankan ruff check + ruff format check di dalam container
lint: build
	$(DOCKER_RUN) sh -c "ruff check . && ruff format --check ."

## unit: jalankan pytest (integrasi PostgreSQL) via docker compose; DB dibuang setelahnya
unit: build
	TEST_IMAGE=$(IMAGE_NAME) $(COMPOSE_TEST) up --abort-on-container-exit --exit-code-from test --remove-orphans; \
	code=$$?; \
	TEST_IMAGE=$(IMAGE_NAME) $(COMPOSE_TEST) down -v --remove-orphans >/dev/null 2>&1; \
	exit $$code

## test: gate lengkap = lint + unit. Dipakai LOKAL dan CI (identik).
test: lint unit

## test-arm64: bangun image runtime linux/arm64 lalu uji asap (aarch64, impor paket, pg_dump 16); BUKAN bagian `make test`
ARM64_IMAGE ?= $(shell basename $(CURDIR))-arm64
test-arm64:
	docker buildx build --platform linux/arm64 --load -f Dockerfile -t $(ARM64_IMAGE) .
	docker run --rm --platform linux/arm64 --entrypoint sh $(ARM64_IMAGE) -c '\
	  set -e; \
	  [ "$$(uname -m)" = "aarch64" ] || { echo "arsitektur bukan aarch64"; exit 1; }; \
	  python -c "import anjab_abk_backend, psycopg; print(psycopg.__version__)"; \
	  pg_dump --version | grep -q " 16\."; \
	  pg_dump --version; \
	  echo "uji asap arm64 OK"'

## migration: buat revisi Alembic baru dari perubahan model — m="deskripsi" (satu berkas/perubahan)
migration: build
	@[ -n "$(m)" ] || { echo 'Pakai: make migration m="deskripsi perubahan"'; exit 1; }
	@TEST_IMAGE=$(IMAGE_NAME) ./scripts/make_migration.sh "$(m)"

## clean: hapus image test
clean:
	-docker rmi $(IMAGE_NAME)

## shell: masuk ke shell container test (debugging)
shell: build
	docker run --rm -it $(IMAGE_NAME) sh

## backup: dump database ke backups/ (DATABASE_URL wajib di-set di env)
backup:
	@./scripts/backup.sh backups

## restore: restore database dari DUMP_FILE=<path> (DATABASE_URL wajib di-set di env)
restore:
	@[ -n "$(DUMP_FILE)" ] || { echo "Pakai: make restore DUMP_FILE=<path/ke/file.dump>"; exit 1; }
	@./scripts/restore.sh "$(DUMP_FILE)"

## backup-list: tampilkan daftar file backup di backups/
backup-list:
	@ls -lht backups/*.dump 2>/dev/null || echo "(belum ada file backup di backups/)"
