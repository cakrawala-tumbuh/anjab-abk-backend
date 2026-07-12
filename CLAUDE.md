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

### [2026-07-13] Penugasan massal (bulk) TS/TI/OPM + auto-populate SME panel di TI

Sebelumnya hanya WCP/DCS punya penugasan bulk (dari revisi `2026-07-12` di
bawah); TS dan TI hanya single, dan meski TI punya jabatan+SME-panel seperti
OPM, anggotanya tidak otomatis jadi responden (beda dari OPM yang sudah
begitu sejak awal). Perubahan:

- **Endpoint bulk baru, berdampingan dengan endpoint single (tidak diganti)**:
  `POST /time-study/penugasan/bulk`, `POST .../task-inventory/sesi/{id}/responden/bulk`,
  `POST .../opm/sesi/{id}/responden/bulk`. Response `BulkAssignResult[T]`
  (`schemas/common.py`, generic mengikuti pola `Page[T]`):
  `{created: T[], skipped: [{partisipan_id, alasan}]}`.
- **Bulk bersifat idempoten (skip-on-conflict), BUKAN atomik** seperti
  WCP/DCS — tiap `partisipan_id` yang gagal (sudah terdaftar/duplikat
  input/bukan anggota panel/kapasitas penuh) dilewati & dilaporkan di
  `skipped`, sisanya tetap dibuat. Urutan pengecekan tetap: dedup input →
  (TI/OPM) keanggotaan SME panel → sudah terdaftar → (TI/OPM) kapasitas
  `max_responden` (dihitung termasuk baris baru dalam batch yang sama).
  String alasan (`sudah_terdaftar`, `duplikat_input`,
  `bukan_anggota_sme_panel`, `kapasitas_penuh`) identik lintas TS/TI/OPM.
- **TS**: `sudah_terdaftar` dideteksi via pre-check SELECT (bukan
  `begin_nested()` per baris + tangkap `IntegrityError` dalam loop) —
  pola savepoint-per-item terbukti TIDAK aman dipakai berulang: satu
  `IntegrityError` tertangkap memaksa `Session` di-`rollback()` penuh
  sebelum bisa dipakai lagi, dan `rollback()` itu ikut membuang baris lain
  yang sudah berhasil di-flush pada iterasi sebelumnya (belum `commit`).
  Lihat komentar di `ts/services/penugasan_sql.py::create_banyak`.
- **TI: sesi baru otomatis mendapat responden dari SME panel jabatannya**
  (`SqlTiSesiService.create()`, meniru pola auto-populate yang sudah ada di
  OPM) — bila panel ada & punya ≥1 anggota; panel tidak ada/kosong → sesi
  tetap dibuat kosong (tidak error, tidak berubah dari perilaku sebelumnya).
  Logika insert-banyak-responden TI ada di **satu** fungsi level-modul,
  `assign_ti_responden_banyak()` (`taskinv/services/responden_sql.py`),
  dipakai baik oleh auto-populate maupun endpoint bulk manual — fungsi ini
  sendiri **tidak** memvalidasi keanggotaan panel (pemanggil yang menyaring).
  `nama` responden auto-populate/bulk **diresolusi dari `PartisipanModel`**
  (bukan `None`) — konsisten dengan pola OPM yang sudah lebih dulu melakukan
  ini; ditemukan lewat E2E `opm.spec.ts` (`anjab-abk-web-app`) yang gagal
  karena responden auto-populate tampil sebagai "Anonim" di tabel (frontend
  hanya menampilkan `r.nama`, tidak melakukan lookup terpisah ke partisipan),
  membuat guard idempoten E2E berbasis nama tidak mendeteksinya dan
  menambahkan responden duplikat.
- **OPM**: `nama`/`jabatan_label` payload bulk diresolusi otomatis dari
  `PartisipanModel`/`JabatanModel` (beda dari endpoint single yang mewajibkan
  `jabatan_label` manual) — mengikuti pola auto-populate OPM yang sudah ada.
- Duplikat `TiRespondenModel`/`OpmRespondenModel` untuk `(sesi_id,
  partisipan_id)` yang sama tetap mungkin terjadi bila endpoint single
  (tidak disentuh) dipanggil untuk partisipan yang sudah di-auto-
  populate/bulk-assign — tidak ada `UNIQUE` constraint DB untuk ini, celah
  pre-existing, di luar lingkup revisi ini.
- **Bug nyata ditemukan lewat E2E langsung** (bukan unit test — lihat Gotcha
  di bawah): `SqlTiSesiService.create()` WAJIB men-`flush()` `rec` (baris
  `TiSesiModel`) SENDIRI, segera setelah `self._s.add(rec)`, **sebelum**
  memanggil `assign_ti_responden_banyak()`. Tanpa flush eksplisit ini,
  urutan `INSERT` saat flush gabungan (sesi + responden dalam satu
  `session.flush()`) TIDAK terjamin oleh SQLAlchemy — unit-of-work
  mengurutkan INSERT berdasarkan `relationship()` ORM yang dikonfigurasi
  antar model, **bukan** sekadar `ForeignKey` kolom mentah.
  `TiRespondenModel.sesi_id` adalah FK murni tanpa `relationship()` balik ke
  `TiSesiModel` (beda dari `TiSesiTaskTerpilihModel` yang punya
  `relationship(back_populates=...)`), jadi tanpa flush eksplisit, flush
  gabungan bisa mencoba INSERT `ti_responden` sebelum baris `ti_sesi` ada →
  `psycopg.errors.ForeignKeyViolation`. **Bug ini SELALU lolos test unit**
  (harness test pakai `Session(..., join_transaction_mode="create_savepoint")`
  yang mem-flush dengan urutan berbeda dari `get_sessionmaker()` produksi)
  — hanya kelihatan lewat E2E nyata (browser + uvicorn + PostgreSQL asli).
  **OPM's `SqlOpmSesiService.create()` punya pola bare-FK yang identik**
  untuk `OpmRespondenModel` (auto-responden dari panel) — berpotensi bug
  yang sama, TAPI di luar lingkup revisi ini untuk diperbaiki (kebetulan
  belum pernah termanifestasi di test yang ada); catat sebagai risiko bila
  disentuh di masa depan.

### [2026-07-12] DCS & WCP: hapus entitas sesi, ganti pola singleton + penugasan langsung

DCS dan WCP tidak lagi memakai sesi — meniru pola yang sudah dipakai Time Study
(`TsPenugasanModel`, lihat entri `[2026-07-04]` di bawah). TI dan OPM (sesi
jabatan) **tidak disentuh**. Perubahan:

- `DcsSesiModel`/`WcpSesiModel` **dihapus**, diganti `DcsInstrumenModel`/
  `WcpInstrumenModel` (tabel `dcs_instrumen`/`wcp_instrumen`) — **singleton**:
  satu baris tetap (`id='dcs'`/`id='wcp'`) dibuat oleh migrasi. Tidak ada
  endpoint create/delete instrumen — hanya `get()`/`update()` (min_responden,
  catatan) dan transisi `tutup()`/`buka_ulang()`/`set_analyzed()`.
- Status instrumen: `OPEN → CLOSED → ANALYZED` (tanpa `DRAFT`; sudah `OPEN`
  sejak migrasi). Reopen `CLOSED → OPEN` diizinkan selama belum `ANALYZED`.
  `_VALID_TRANSITIONS = {"OPEN": {"CLOSED"}, "CLOSED": {"OPEN", "ANALYZED"},
  "ANALYZED": set()}`.
- Kolom `periode` dan `max_responden` **dihapus** (1 deployment = 1 studi;
  tidak ada lagi batas atas jumlah responden — hanya `min_responden` sebagai
  cutoff analisis, default 6).
- `DcsRespondenModel`/`WcpRespondenModel` kehilangan `sesi_id` (+FK); kolom
  `partisipan_id` menjadi `UNIQUE` lintas SELURUH responden (PostgreSQL
  mengizinkan banyak `NULL` — responden anonim tetap boleh berulang).
- **Penugasan (assign) bersifat bulk**: `POST /dcs/responden` (atau
  `/wcp/responden`) menerima `{"partisipan_ids": [...]}` (list, minimal 1),
  atomik dalam satu transaksi. `nama`/`jabatan_label` responden diisi OTOMATIS
  dari `PartisipanService` (`nama`, `jabatan_utama_id`) — payload TIDAK lagi
  menerima `nama`/`jabatan_label` per baris, sehingga responden ANONIM (tanpa
  `partisipan_id`) tidak lagi bisa dibuat lewat endpoint publik manapun untuk
  DCS/WCP. `jabatan_label` tetap kolom teks bebas (bukan FK) — nilainya
  sekadar disalin dari `jabatan_utama_id`, bukan diresolusi ke nama jabatan
  (di luar lingkup revisi ini).
- Endpoint peta baru: `GET/PATCH /dcs/instrumen`, `POST /dcs/instrumen/tutup`,
  `POST /dcs/instrumen/buka-ulang`, `GET/POST /dcs/responden`, `GET/DELETE
  /dcs/responden/{id}`, `PUT/POST/GET /dcs/responden/{id}/jawaban*`,
  `POST /dcs/analisis`, `GET /dcs/hasil`, `GET /dcs/hasil-responden/{id}`,
  `GET /dcs/kuesioner/saya` (idem `/wcp/...`). Seluruh endpoint lama
  `.../sesi/{sesi_id}/...` **dihapus total tanpa deprecation**.
- K-Index DCS: parameter query `wcp_sesi_id` **dihapus** — `POST
  /dcs/analisis` & `GET /dcs/hasil` selalu membaca instrumen WCP satu-satunya;
  `k_index`/`k_index_wcp_risk` bernilai `null` hanya bila WCP belum punya
  responden ber-submit (bukan lagi karena parameter tak disertakan).
- `compute_hasil_sesi()` → `compute_hasil()` (DCS & WCP): parameter `sesi`
  dihapus (tidak ada lagi `sesi_id`/`periode` di respons hasil); LOGIKA
  STATISTIK (mean/stdev/Cronbach alpha/risk_flag/k_index) **tidak berubah**.
- Migrasi (`3b10e24fa970`, satu berkas mencakup DCS & WCP) menolak jalan
  (`RuntimeError`, pesan menyebut `sesi_id` bermasalah) bila ditemukan >1 sesi
  DCS/WCP yang MASING-MASING punya ≥1 responden. `min_responden`/`catatan`/
  status disalin dari sesi ber-responden bila ada; default dipakai bila tidak
  ada (`status=OPEN`, `min_responden=6`, `catatan=NULL`). Downgrade
  best-effort (struktur lama dipulihkan kosong, data tak direkonstruksi),
  mengikuti konvensi `0a58616358f4`.

### [2026-07-12] Force-delete sesi admin (`paksa=true`) + FK `ON DELETE CASCADE`

Dua perbaikan terkait DELETE sesi (DCS/WCP/OPM/Task Inventory):

- **`DELETE .../sesi/{sesi_id}?paksa=true`.** Sebelumnya sesi non-DRAFT MUSTAHIL
  dihapus (`status != "DRAFT"` selalu ditolak), padahal `status` tidak dapat
  di-`PATCH` dan transisi hanya maju-satu-arah — admin tidak punya jalan keluar.
  Endpoint sudah admin-only; ditambah query param opsional `paksa: bool = False`
  mengikuti preseden `mulai-tahap2`/`mulai-tahap3` (`taskinv_sesi.py`). Tanpa
  `paksa`, sesi non-DRAFT tetap ditolak (422, pesan menyebut `paksa=true`); dengan
  `paksa=true`, sesi dihapus di status apa pun. Kontrak tetap `204 No Content`
  (tidak ada body konfirmasi tambahan). `logger.warning` mencatat aktor tiap kali
  `paksa=True` dipakai.
- **FK `ON DELETE CASCADE` di 12 kolom `sesi_id`/`responden_id`.** Kolom-kolom ini
  sebelumnya `String(40)` tanpa constraint — menghapus sesi/responden lewat API
  meninggalkan baris responden & jawaban YATIM yang tak terjangkau API mana pun.
  Migrasi `a4aeb5bcbe81` membersihkan baris yatim yang sudah ada (urutan: responden
  yatim dulu, baru jawaban/seleksi/detail/tahap2 yatim — turunan langkah pertama)
  sebelum membuat FK. `SqlXSesiService.delete()` memanggil `session.expire_all()`
  setelah hapus (anak sudah lenyap di DB via CASCADE, identity map jadi basi).
  Sengaja **tidak** dipakai `relationship(cascade="all, delete-orphan")` — akan
  memaksa ORM memuat ribuan baris jawaban ke memori; cascade DB-level saja cukup
  dan otomatis berlaku juga untuk `responden.delete()` yang sudah ada (menambal bug
  tak terlaporkan: dulu jawaban tidak ikut terhapus saat responden dihapus).
  `opm_sesi.ti_sesi_id` **sengaja tidak** diberi FK (di luar revisi ini — akan
  bertabrakan dengan force-delete sesi TI, perlu keputusan RESTRICT vs lainnya).

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
- **Membuat parent + child ORM baru dalam satu `create()` (mis. sesi + auto-populate anak)**: bila kolom FK anak (`ForeignKey(...)`) TIDAK punya `relationship()` ORM balik ke parent, `session.flush()` gabungan TIDAK menjamin urutan INSERT parent-dulu — flush parent SENDIRI (`self._s.add(parent); self._s.flush()`) sebelum menambah anak, jangan andalkan urutan otomatis. Bug ini lolos test unit (harness pakai `join_transaction_mode="create_savepoint")`, beda perilaku dari `get_sessionmaker()` produksi) — hanya kelihatan lewat E2E/produksi nyata. Lihat entri `[2026-07-13]` di Revisi Desain untuk kasus nyata (`SqlTiSesiService.create()`).

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
