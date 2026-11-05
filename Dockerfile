# Image RUNTIME aplikasi (bukan image test — itu milik skill `automated-test`).
# Multi-stage: stage `builder` membuat wheel, stage `runtime` ramping tanpa toolchain.
# Berjalan sebagai user non-root.
# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder
ENV PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
RUN pip install --upgrade build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m build --wheel --outdir /dist

FROM python:3.12-slim AS runtime
ARG GIT_COMMIT=unknown
LABEL org.opencontainers.image.title="anjab-abk-backend" \
      org.opencontainers.image.description="Backend REST API ANJAB & ABK yayasan pendidikan." \
      org.opencontainers.image.source="https://github.com/OWNER/anjab-abk-backend" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LOG_LEVEL=INFO \
    APP_BUILD_COMMIT=${GIT_COMMIT}

WORKDIR /app
COPY --from=builder /dist/*.whl /tmp/
RUN pip install /tmp/*.whl \
    && rm -rf /tmp/*.whl \
    && useradd --create-home --uid 1000 appuser

# postgresql-client-16 dari repositori resmi PGDG (apt.postgresql.org) — WAJIB versi 16,
# bukan paket `postgresql-client` bawaan Debian bookworm (versi 15): produksi memakai
# PostgreSQL 16, dan `pg_dump`/`pg_restore` 15 MENOLAK melayani server 16 ("server version
# mismatch"). Dipakai oleh endpoint admin backup/restore (backlog 025, services/backup.py).
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        | gpg --dearmor -o /usr/share/keyrings/postgresql.gpg \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/keyrings/postgresql.gpg] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client-16 \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/* /etc/apt/sources.list.d/pgdg.list

# Claude Code (binary `claude`) untuk penyedia LANGGANAN_CLAUDE (backlog 112). Dipasang dari
# repo apt bertanda tangan kanal `stable` dan DIPIN ke satu versi. Kunci penandatangan
# diperiksa terhadap sidik jari PENUH (40 heksa, bukan ID pendek); beda satu karakter pun
# membuat build gagal. Menaikkan versi = mengubah ARG ini (dan memeriksa ulang uji asap).
# Model baru dapat menuntut versi lebih baru dari yang dipin di sini.
ARG CLAUDE_CODE_VERSION=2.1.311-1
ARG CLAUDE_CODE_SIGNING_FPR=31DDDE24DDFAB679F42D7BD2BAA929FF1A7ECACE
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://downloads.claude.ai/keys/claude-code.asc -o /etc/apt/keyrings/claude-code.asc \
    && fpr="$(gpg --show-keys --with-colons /etc/apt/keyrings/claude-code.asc \
        | awk -F: '/^pub:/ {p=1; next} p && /^fpr:/ {print $10; p=0}')" \
    && if [ "$fpr" != "${CLAUDE_CODE_SIGNING_FPR}" ]; then \
        echo "Sidik jari kunci Claude Code tidak cocok: '$fpr' != '${CLAUDE_CODE_SIGNING_FPR}'" >&2; \
        exit 1; \
    fi \
    && echo "deb [signed-by=/etc/apt/keyrings/claude-code.asc] https://downloads.claude.ai/claude-code/apt/stable stable main" \
        > /etc/apt/sources.list.d/claude-code.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends "claude-code=${CLAUDE_CODE_VERSION}" \
    && apt-get purge -y --auto-remove curl gnupg \
    && rm -rf /var/lib/apt/lists/* /etc/apt/sources.list.d/claude-code.list

# Direktori sesi masuk CLI. Berada di image (bukan konfigurasi deployment); isinya diisi
# operator lewat alur masuk Anthropic sendiri, tidak pernah oleh aplikasi. Mount volume di
# sini agar sesi masuk bertahan; volume baru milik root bila tak ada direktori ini lebih dulu.
ENV CLAUDE_CONFIG_DIR=/var/lib/claude-config \
    DISABLE_UPDATES=1
RUN mkdir -p "${CLAUDE_CONFIG_DIR}" \
    && chown appuser:appuser "${CLAUDE_CONFIG_DIR}" \
    && chmod 700 "${CLAUDE_CONFIG_DIR}"

# Migrasi & entrypoint ikut ke image agar init DB OTOMATIS saat startup (tanpa langkah
# deploy manual). Paket di-install ke site-packages, jadi alembic.ini + migrations/
# disalin ke WORKDIR (/app) tempat `migrate._resolve_base()` & alembic CLI menemukannya.
COPY alembic.ini ./
COPY migrations ./migrations
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).status==200 else 1)"]

# Entrypoint menjalankan `initdb` (migrasi + seed, idempoten) lalu exec CMD.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "anjab_abk_backend"]
