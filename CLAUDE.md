# anjab-abk-backend — Backend FastAPI (ANJAB & ABK, Yayasan Pendidikan)

Ikhtisar & cara pakai (untuk manusia): lihat README.md.
Konteks domain (yayasan pendidikan, jenjang sekolah, struktur UnitKerja): lihat CLAUDE.md repo induk.

## Perintah

@Makefile

## Struktur / Arsitektur

**Modular Monolith** — tiga domain dalam satu service, dibedakan lewat modul Python.

```
src/anjab_abk_backend/
├── core/           # entitas & service bersama (UnitKerja, dll.)
├── anjab/          # domain Analisis Jabatan (Jabatan, UraianJabatan, SyaratJabatan)
├── abk/            # domain Analisis Beban Kerja (BebanKerja, HasilABK)
├── api/v1/         # router per domain, semua di-mount ke /api/v1/
├── services/       # seam akses data (Protocol + impl PostgreSQL)
├── main.py         # create_app() factory
├── config.py       # pydantic-settings (app, CORS, auth, DB)
├── openapi.py      # metadata OpenAPI + tag
└── errors.py       # envelope error + handlers
```

Setiap domain punya **model ORM**, **skema Pydantic**, dan **seam service** sendiri —
tidak boleh lintas domain kecuali lewat `core`.

- Entrypoint: `python -m anjab_abk_backend` (atau `uvicorn anjab_abk_backend.main:app`)
- Migrasi: `alembic upgrade head`

## Migrasi Database (mekanisme inkremental, gaya Odoo)

Setiap perubahan struktur database = **satu berkas revisi Alembic baru** di
`migrations/versions/` — JANGAN menumpuk banyak perubahan ke satu berkas, JANGAN
mengedit revisi yang sudah pernah berjalan. Tiap revisi menyimpan `down_revision`
sehingga membentuk rantai terurut yang diterapkan bertahap dari versi DB saat ini ke
`head`.

Alur saat model (`models.py`) berubah:

1. Ubah model ORM.
2. `make migration m="deskripsi perubahan"` — autogenerate revisi baru (pakai DB
   ephemeral; berkas baru muncul di `migrations/versions/`).
3. **Review** berkas revisi, sesuaikan bila perlu (autogenerate tak selalu sempurna).
4. `alembic upgrade head` untuk menerapkan.

Runner terprogram ada di `src/anjab_abk_backend/migrate.py` (dipakai test & tooling).

**Penjaga (di `tests/test_migrations.py`)**: `test_schema_matches_models` gagal bila
model berubah tanpa revisi baru; `test_single_head` mencegah cabang divergen; harness
test membangun schema lewat `alembic upgrade head` (bukan `create_all`) sehingga tiap
run test ikut memverifikasi migrasi.

## Konvensi & Invariants

- Setiap endpoint wajib punya `response_model`, `summary`, `tags`, dan `responses` error.
- ID selalu UUID v4; tidak pakai auto-increment integer.
- Error **selalu** keluar via envelope `errors.py` — jangan `raise HTTPException` mentah.
- Search memakai domain bergaya Odoo (`[field, operator, value]`) — validasi di `services/domain.py`.
- Akses data ke domain lain hanya via seam service `core` — tidak query lintas domain langsung.
- Prefix versi API: `/api/v1/`.
- Autentikasi via JWT Authentik (RS256, JWKS); backend hanya memvalidasi token, tidak menerbitkan.

## Revisi Desain

### [2026-06-21] DCS & WCP: Sesi tidak terikat jabatan

Sesi DCS dan WCP tidak lagi memerlukan `jabatan_id`. Partisipan dengan jabatan apapun
dapat di-assign ke sesi yang sama. Perubahan:
- `DcsSesiCreate` / `WcpSesiCreate`: field `jabatan_id` dihapus.
- `DcsSesiRead` / `WcpSesiRead`: field `jabatan_id` dihapus.
- `DcsHasilSesiRead` / `WcpHasilSesiRead`: field `jabatan_id` dihapus.
- `DcsKuesionerItemRead` / `WcpKuesionerItemRead`: field `sesi_jabatan_id` dihapus.
- Uniqueness check `(jabatan_id, periode)` di service dihapus — admin bebas buat sesi sebanyak yang diperlukan per periode.
- `SEARCHABLE_FIELDS` sesi DCS/WCP tidak lagi mengandung `jabatan_id`.

### [2026-06-21] DCS & WCP: Enrollment berbasis Assignment

DCS dan WCP beralih dari **enrollment otomatis** ke **sistem assignment**:

- Partisipan **hanya** melihat kuesioner yang sudah di-assign admin secara eksplisit
  (record `responden` dibuat admin via `POST /api/v1/{dcs|wcp}/sesi/{sesi_id}/responden`
  dengan field `partisipan_id` diisi).
- Endpoint `GET /kuesioner/saya` tidak lagi membuat record responden otomatis;
  ia hanya membaca hasil `list_by_partisipan()`.
- Method `ensure_for_partisipan()` telah dihapus dari `DcsRespondenService` dan
  `WcpRespondenService` (Protocol + InMemory impl).
- Setiap alat ukur (DCS, WCP) dapat di-assign secara mandiri ke partisipan berbeda.
- Task Inventory tetap menggunakan flow yang sama (assignment manual via `tambah-responden`).

## Jangan Sentuh

- `migrations/versions/` — migrasi historis yang sudah berjalan; jangan diedit tangan (buat revisi baru).
- `openapi.json` — di-generate `make export-openapi`; jangan edit tangan.
- `src/anjab_abk_backend/security.py` kontrak `TokenVerifier` — seam ini diisi `backend-authentik-skill`, jangan ubah signature-nya.

## Gotcha

- Test butuh env `DATABASE_URL` dan `AUTHENTIK_ISSUER` (lihat `.env.example`); tanpa itu beberapa test bisa gagal senyap.
- `make test` menjalankan linter + unit di dalam Docker — tidak ada artefak di folder project setelah selesai.
- Authentik JWKS di-cache; perubahan kunci di Authentik membutuhkan restart service atau cache TTL habis.
- Endpoint OAuth2 Swagger (`/docs/oauth2-redirect`) wajib didaftarkan di Authentik sebagai Redirect URI.

## Alur Kerja & Definition of Done

- Sebelum lapor selesai: `make test` hijau (lint + unit). Branch utama: `master`.
- Commit/branch/PR/tag → skill `git-workflow`; eksekusi `gh` → skill `github-cli-skill`.
- Gate test → skill `automated-test`; docstring → skill `docstring`; README → skill `readme`.

## Delegasi Skill

| Tugas | Skill |
|---|---|
| Scaffold backend FastAPI (router, skema, Swagger, error, keamanan, observability) | `backend-skill` |
| Mengisi seam autentikasi (Authentik OIDC, JWKS, otorisasi group) | `backend-authentik-skill` |
| Mengisi seam akses data (SQLAlchemy 2.0 + psycopg 3 + Alembic → PostgreSQL) | `backend-postgresql-skill` |
| README.md (pintu depan repo) | `readme-skill` |
| Gate test (lint + unit, Makefile + Docker, lokal == CI) | `automated-test-skill` |
| Commit, branch, PR, tag/release semver, changelog | `git-workflow-skill` |
| Eksekusi perintah `gh` (PR, release, Actions) | `github-cli-skill` |
| Docstring kelas/fungsi/endpoint | `docstring-skill` |
| Orkestrasi deploy (Docker Compose + Traefik, env rahasia) | `copier-docker-compose-skill` |
