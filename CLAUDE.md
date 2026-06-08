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

## Konvensi & Invariants

- Setiap endpoint wajib punya `response_model`, `summary`, `tags`, dan `responses` error.
- ID selalu UUID v4; tidak pakai auto-increment integer.
- Error **selalu** keluar via envelope `errors.py` — jangan `raise HTTPException` mentah.
- Search memakai domain bergaya Odoo (`[field, operator, value]`) — validasi di `services/domain.py`.
- Akses data ke domain lain hanya via seam service `core` — tidak query lintas domain langsung.
- Prefix versi API: `/api/v1/`.
- Autentikasi via JWT Authentik (RS256, JWKS); backend hanya memvalidasi token, tidak menerbitkan.

## Jangan Sentuh

- `alembic/versions/` — migrasi historis yang sudah berjalan; jangan diedit tangan.
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
