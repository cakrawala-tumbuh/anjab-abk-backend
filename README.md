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

### Feature flag

Lima fungsi dapat dimatikan independen lewat env, semuanya default `false` (fail-closed):
`FEATURE_AI_NARRATIVE_DRAFT`, `FEATURE_PARTICIPANT_VALIDATION`, `FEATURE_WCP_DCS_SCORING`,
`FEATURE_RESEARCH_EXPORT`, `FEATURE_CHANGE_AUTHORIZATION`. Perubahan butuh restart. Status
dapat dibaca (bertoken) lewat `GET /api/v1/system/fitur`.

### Menyalakan AI

AI menyala hanya bila semua syarat ini terpenuhi; memilih penyedia tidak dengan sendirinya
menyalakan AI:

1. Flag `FEATURE_AI_NARRATIVE_DRAFT=true` (env, butuh restart) dan saklar layanan AI hidup.
2. `AI_JENIS_SUMBER_DIIZINKAN` (env) mengizinkan jenis sumber yang dipakai; bawaan hanya
   `["SINTETIS"]`. Gerbang data (jenis sumber, PII, flag, saklar) sama untuk semua penyedia.
3. `AI_FUNGSI_AKTIF` (env) mendaftarkan fungsi AI yang boleh dipakai.
4. Penyedia siap lewat UI admin (disimpan di basis data, berlaku pada job berikutnya tanpa
   restart): `API_ANTHROPIC` dengan kunci API terpasang, atau `LANGGANAN_CLAUDE` dengan CLI
   yang sudah masuk (paket langganan Anthropic, bukan Anthropic API; driver menyusul).
   Mode `MATI` (bawaan) membuat pengajuan ditolak dan job antre selesai manual
   `PENYEDIA_MATI`. `AI_KREDENSIAL_KUNCI_INDUK` (env) wajib untuk menyimpan kunci API.
5. Keputusan tertulis K-8 untuk membuka jenis sumber di luar `SINTETIS`.

Env `ANTHROPIC_API_KEY`, `AI_MODEL`, dan `AI_EFFORT` tidak lagi dibaca; model, effort, dan
kunci hanya berasal dari pengaturan penyedia. Tiap `ai_run` mencatat `penyedia`.
