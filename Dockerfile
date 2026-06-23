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
LABEL org.opencontainers.image.title="anjab-abk-backend" \
      org.opencontainers.image.description="Backend REST API ANJAB & ABK yayasan pendidikan." \
      org.opencontainers.image.source="https://github.com/OWNER/anjab-abk-backend" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LOG_LEVEL=INFO

WORKDIR /app
COPY --from=builder /dist/*.whl /tmp/
RUN pip install /tmp/*.whl \
    && rm -rf /tmp/*.whl \
    && useradd --create-home --uid 1000 appuser

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
