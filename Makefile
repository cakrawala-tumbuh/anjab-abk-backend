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

# Evaluasi perilaku model (`eval-ai`): di luar `make test`. Nilai dari baris perintah/env
# diteruskan ke resep LEWAT ENVIRONMENT dan dirujuk sebagai "$$VAR" (bukan $(VAR)), sehingga
# nilai berbahaya ($(...), spasi, ;, path) tidak pernah ditafsirkan shell.
EVAL_BASE_IMAGE ?= $(shell basename $(CURDIR))-eval-base
EVAL_IMAGE ?= $(shell basename $(CURDIR))-eval
export FUNGSI PENYEDIA CLAUDE_VOLUME EVAL_ULANG EVAL_MAKS_TOKEN

.DEFAULT_GOAL := test
.PHONY: build lint unit test clean shell help \
        migration backup restore backup-list test-arm64 eval-ai

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
	  claude --version | grep -q "^2\.1\.311"; \
	  claude --version; \
	  echo "uji asap arm64 OK"'

## eval-ai: evaluasi perilaku model di luar `make test` — FUNGSI=<P01|P09|P10> PENYEDIA=<API_ANTHROPIC|LANGGANAN_CLAUDE> [CLAUDE_VOLUME=<volume>]; lihat README
# `make` mengubah kegagalan resep jadi exit 2: baca kode harness dari baris akhir `#EVAL`.
# Jalur API: kunci dari env `ANTHROPIC_API_KEY` milik operator, diteruskan TANPA nilai di
# argumen (`-e ANTHROPIC_API_KEY`). Jalur langganan: volume Docker bernama, tanpa env kunci.
eval-ai:
	@LC_ALL=C; export LC_ALL; \
	case "$$FUNGSI" in \
	  ''|*[!A-Za-z0-9_]*) echo 'FUNGSI wajib berupa kode fungsi, mis. FUNGSI=P10.' >&2; exit 2 ;; \
	esac; \
	case "$$PENYEDIA" in \
	  API_ANTHROPIC) ;; \
	  LANGGANAN_CLAUDE) \
	    case "$$CLAUDE_VOLUME" in \
	      ''|[!A-Za-z0-9]*|*[!A-Za-z0-9_.-]*) \
	        echo 'CLAUDE_VOLUME wajib nama volume Docker bernama (huruf/angka/_/./-), bukan path.' >&2; exit 2 ;; \
	    esac ;; \
	  *) echo 'PENYEDIA wajib API_ANTHROPIC atau LANGGANAN_CLAUDE.' >&2; exit 2 ;; \
	esac
	docker build --target runtime -t $(EVAL_BASE_IMAGE) .
	docker build -f Dockerfile.eval --build-arg BASE_IMAGE=$(EVAL_BASE_IMAGE) -t $(EVAL_IMAGE) .
	@if [ "$$PENYEDIA" = API_ANTHROPIC ]; then \
	  docker run --rm -e ANTHROPIC_API_KEY -e AI_INFERENCE_GEO=us -e AI_REFUSAL_FALLBACK=false \
	    -e EVAL_ULANG -e EVAL_MAKS_TOKEN $(EVAL_IMAGE) --fungsi "$$FUNGSI" --penyedia "$$PENYEDIA"; \
	else \
	  docker run --rm -v "$$CLAUDE_VOLUME":/var/lib/claude-config \
	    -e EVAL_ULANG -e EVAL_MAKS_TOKEN $(EVAL_IMAGE) --fungsi "$$FUNGSI" --penyedia "$$PENYEDIA"; \
	fi

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
