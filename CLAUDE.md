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

**Deploy: init DB otomatis (tanpa langkah manual).** Image runtime menyertakan
`alembic.ini` + `migrations/`; `docker-entrypoint.sh` menjalankan
`python -m anjab_abk_backend.initdb` (migrasi + seed) sebelum app naik. Idempoten &
aman diulang tiap `up -d` (tabel `alembic_version` mencegah migrasi diulang; seed
melompati baris yang sudah ada). `create_app()` TIDAK menjalankan migrasi (bebas efek
samping). Dirancang untuk **satu instance**; multi-replica → jadikan `initdb` job init terpisah.

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

### [2026-07-08] DCS/WCP/OPM/Task Inventory Tahap1&3: pisah draft-save dari submit final

Semua instrumen yang tadinya "submit sekali jadi" (satu `POST` bulk yang wajib
lengkap & langsung mengunci status) sekarang mendukung simpan progres bertahap
sebelum finalisasi. Pola diseragamkan di 5 lokasi: DCS jawaban, WCP jawaban, OPM
jawaban, Task Inventory seleksi (Tahap 1), Task Inventory detail (Tahap 3).
Time Study (sudah resumable secara alami via CRUD log harian) dan Task Inventory
Tahap 2 (keputusan koordinator, bukan partisipan) tidak disentuh.

- **`PUT .../jawaban`** (atau `.../seleksi`, `.../detail`) — endpoint baru, upsert
  payload **parsial** (boleh 0..N item, `*BulkCreate`/`*Submit` lama diganti
  `*Upsert`/`*DraftSave` dengan `min_length` dihapus). Insert baris baru atau
  update baris existing per unique key (`(responden_id, item_id)` untuk
  DCS/WCP/OPM jawaban & TI detail; `(responden_id, task_kode)` untuk TI detail).
  Ditolak (422) bila responden sudah submit final. TI-Seleksi memakai semantik
  **full-replace** (hapus semua baris lama punya responden, insert set baru) —
  paling natural untuk representasi "pilihan saat ini" sebuah checkbox set.
- **`POST .../jawaban/submit`** (atau `.../seleksi/submit`, `.../detail/submit`)
  — endpoint baru, **tanpa body**. Memvalidasi baris yang sudah tersimpan di DB
  memenuhi syarat kelengkapan (DCS 42 item, WCP 72 item, OPM & TI-Detail: subset
  valid tanpa kekurangan/asing, TI-Seleksi: minimal 1 task terpilih), lalu
  menandai flag submit (`sudah_submit`/`tahap1_submit`/`tahap3_submit`) +
  timestamp.
- **`POST .../jawaban`** (lama, bulk sekali jadi) **dihapus** — bukan
  dipertahankan sebagai alias. Frontend memanggil `PUT` (simpan) lalu
  `POST .../submit` (finalisasi) berurutan; tombol "Simpan" hanya memanggil
  `PUT`.
- Service Protocol tiap instrumen: method `bulk_create()`/`submit()` lama diganti
  `upsert()` (atau `save_draft()` untuk TI-Seleksi) + `submit()` baru yang hanya
  memvalidasi dari DB (tanpa payload).
- Tidak ada migrasi Alembic — kolom `sudah_submit`/`submitted_at`/
  `tahap1_submit`/`tahap3_submit` yang sudah ada cukup; draft = "baris ada di DB
  tapi flag submit masih `False`".

### [2026-07-04] Time Study: hapus sesi, penugasan berbasis partisipan

Time Study tidak lagi memakai sesi. Mekanisme assign partisipan disederhanakan
menjadi penugasan langsung per partisipan; partisipan mencatat log harian
open-ended (tanpa periode) selama penugasannya aktif. Perubahan:
- `TsSesiModel` & `TsRespondenModel` dihapus; diganti `TsPenugasanModel`
  (`ts_penugasan`: `partisipan_id` unik, flag `aktif`, `catatan`) — satu penugasan
  per partisipan, bukan per sesi.
- `TsLogModel.responden_id` diganti `partisipan_id`; constraint unik berubah dari
  `(responden_id, tanggal)` menjadi `(partisipan_id, tanggal)`.
- State machine `DRAFT→OPEN→CLOSED→ANALYZED` dihapus dari TS; digantikan flag
  `aktif` sederhana. Pencatatan/pembaruan log ditolak (422) saat penugasan nonaktif.
- Endpoint: `/time-study/sesi` & `/time-study/sesi/{sesi_id}/responden` diganti
  `/time-study/penugasan` (CRUD); `/time-study/responden/{responden_id}/log` menjadi
  `/time-study/penugasan/{penugasan_id}/log`.
- `TsKuesionerItemRead` diringkas menjadi `{id, aktif, jumlah_log, created_at}` —
  field `sesi_*` dihapus; endpoint `/kuesioner/saya` memfilter penugasan `aktif`
  (bukan status sesi OPEN).
- Analisis/agregasi Time Study sengaja TIDAK dibangun di revisi ini (di luar
  lingkup) — TS belum punya endpoint hasil/analisis nyata sebelumnya.

### [2026-06-25] Task Inventory: Sesi tidak perlu unit

Sesi Task Inventory tidak lagi memerlukan `unit` (jenjang). Sesi hanya terikat pada
`jabatan_id`. Perubahan:
- `TiSesiCreate` / `TiSesiRead`: field `unit` dihapus; `jabatan_nama` ditambahkan ke `TiSesiRead`.
- `TiHasilSesiRead`: field `unit` dihapus.
- `TiKuesionerItemRead`: field `sesi_unit` dihapus.
- `TiKombinasiRead`: field `jabatan_nama` ditambahkan (nama jabatan dari tabel Jabatan).
- Uniqueness sesi berubah dari `(unit, jabatan_id, periode)` menjadi `(jabatan_id, periode)`.
- Validasi create sesi selalu pakai `valid_kodes_for_jabatan(jabatan_id)`.
- `SEARCHABLE_FIELDS` sesi TI tidak lagi mengandung `unit`.
- Migrasi: kolom `unit` dihapus dari tabel `ti_sesi`.

### [2026-06-25] DCS & WCP: Hilangkan jabatan dari tampilan partisipan

`DcsKuesionerItemRead` dan `WcpKuesionerItemRead` tidak lagi mengekspos `jabatan_label`
ke partisipan. Sebagai gantinya, field `sesi_catatan` (catatan sesi) ditampilkan sebagai
label pengenal sesi di halaman kuesioner partisipan. Perubahan:
- `DcsKuesionerItemRead` / `WcpKuesionerItemRead`: field `jabatan_label` diganti `sesi_catatan: str | None`.
- Endpoint `/kuesioner/saya` DCS dan WCP: mengisi `sesi_catatan` dari `sesi.catatan`.
- `jabatan_label` tetap ada di `DcsRespondenRead` / `WcpRespondenRead` (dipakai admin).

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
