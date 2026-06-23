# anjab-abk-backend

Backend REST API untuk **ANJAB** (Analisis Jabatan) dan **ABK** (Analisis Beban Kerja)
yayasan pendidikan, dibangun dengan **FastAPI**.

## Menjalankan (development)

```bash
pip install -e .
uvicorn anjab_abk_backend.main:create_app --factory --reload
# atau (prod-like):
python -m anjab_abk_backend
```

- Swagger UI  → http://localhost:8000/docs
- ReDoc       → http://localhost:8000/redoc
- Health      → http://localhost:8000/api/v1/health

## Deploy (Docker)

Inisialisasi database **otomatis** — tidak ada langkah manual. Entrypoint container
menjalankan migrasi + seed master data sebelum aplikasi naik:

```bash
docker run -d \
  -e DATABASE_URL="postgresql+psycopg://user:pass@host:5432/dbname" \
  -e AUTHENTIK_ISSUER="https://auth.example.com/" \
  -p 8000:8000 ghcr.io/<owner>/anjab-abk-backend:latest
```

Saat start, entrypoint menjalankan `python -m anjab_abk_backend.initdb`:
`alembic upgrade head` lalu seed master data. **Aman diulang tiap `up -d`/restart** —
tabel `alembic_version` mencegah migrasi lama dijalankan ulang dan seed melompati baris
yang sudah ada (start kedua dst. praktis no-op). Cocok untuk deployment **satu instance**;
untuk multi-replica, jalankan `initdb` sebagai job init terpisah (sekali, sebelum app).

> Migrasi manual (mis. dari checkout source) tetap bisa: `alembic upgrade head`.
> Cara membuat revisi saat model berubah: lihat `CLAUDE.md` → "Migrasi Database".

## Test

```bash
make test   # lint + unit di Docker (gate — dari skill automated-test)
```

## Konfigurasi

Lihat `.env.example`. Semua via environment (12-factor).
