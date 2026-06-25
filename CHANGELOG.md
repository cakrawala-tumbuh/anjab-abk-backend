# Changelog

Semua perubahan penting pada proyek ini didokumentasikan di berkas ini.

Format mengacu pada [Keep a Changelog](https://keepachangelog.com/id/1.1.0/),
dan proyek ini menganut [Semantic Versioning](https://semver.org/lang/id/).

## [Unreleased]

## [0.20.2] - 2026-06-25

### Diperbaiki

- **Contoh OpenAPI sesi DCS & WCP masih mencantumkan `jabatan_id`** — field ini sudah
  dihapus sejak v0.11.0; contoh pada endpoint `POST /api/v1/dcs/sesi` dan
  `POST /api/v1/wcp/sesi` diperbarui agar tidak memuat field yang tidak lagi relevan.

## [0.20.1] - 2026-06-25

### Diuji

- **Test `test_ut_seeded_data_via_catalog_endpoint`** kini memverifikasi bahwa field
  `jabatan_nama` di respons endpoint `/catalog/kombinasi` berisi nama jabatan yang
  sesungguhnya (bukan kode jabatan).

## [0.20.0] - 2026-06-25

### Ditambahkan

- **`jabatan_nama` di `TiSesiRead` dan `TiKombinasiRead`** — respons sesi dan katalog kombinasi
  kini menyertakan nama jabatan yang di-resolve dari tabel `jabatan`, sehingga UI tidak perlu
  menampilkan kode jabatan mentah.

### Diubah

- **Field `unit` dihapus dari sesi Task Inventory** — `TiSesiCreate`, `TiSesiRead`,
  `TiHasilSesiRead`, dan `TiKuesionerItemRead` tidak lagi menyertakan field `unit`.
  Uniqueness sesi berubah dari `(unit, jabatan_id, periode)` menjadi `(jabatan_id, periode)`.
  Validasi create sesi kini selalu menggunakan `valid_kodes_for_jabatan(jabatan_id)`.
- **Migrasi Alembic `d3e6f1a8b9c2`** menghapus kolom `unit` dari tabel `ti_sesi`.
- **`SEARCHABLE_FIELDS` sesi TI** tidak lagi mengandung `unit`.

## [0.19.0] - 2026-06-25

### Diperbaiki

- **Tautan identitas partisipan diselaraskan dengan klaim `sub` (sub_mode=user_email)** —
  provider OAuth2 ANJAB-ABK memakai `sub_mode = user_email`, sehingga `sub` token = email.
  Backend mencocokkan `partisipan.authentik_user_id == sub` saat login. Data lama mengisi
  kolom ini dengan `placeholder_xxxxxxxx` (atau pk numerik Authentik) yang tak pernah sama
  dengan `sub`, sehingga tautan hanya tertolong fallback email di `get_by_subject`. Migrasi
  baru `a1c4e7f9b2d6` mem-backfill `authentik_user_id = email` untuk semua baris yang belum
  cocok, agar pencocokan primer langsung tepat.

### Diubah

- **`AuthentikProvisioner.create_partisipan_user` mengembalikan subject OIDC (email),
  bukan pk numerik** — `HttpAuthentikProvisioner` tetap membuat user di Authentik & memvalidasi
  responsnya, namun mengembalikan email agar konsisten dengan `sub_mode=user_email`;
  `PlaceholderAuthentikProvisioner` juga mengembalikan email (sebelumnya `placeholder_<hex>`).
  Partisipan yang dibuat selanjutnya otomatis punya `authentik_user_id` yang benar.
- **Kolom `partisipan.authentik_user_id` dilebarkan VARCHAR(64) → VARCHAR(254)** agar muat
  email penuh (selebar kolom `email`) tanpa terpotong.

## [0.18.0] - 2026-06-23

### Ditambahkan

- **Catalog Task Inventory diperkaya id hirarki** — `TiCatalogRead` kini menyertakan
  `tugas_pokok_id` dan `detil_tugas_id` (kunci stabil) di samping nama tugas pokok &
  detil tugas yang sudah ada. Diambil langsung dari `UraianTugas` (M2O) sehingga
  konsisten dengan master data. Mendukung seleksi relevansi Tahap 1 bertingkat
  (cascade Tugas Pokok → Detil Tugas → Uraian Tugas) di frontend tanpa mengandalkan
  pencocokan nama. `detil_tugas_id` bernilai null bila task langsung di bawah tugas
  pokok (konsisten dengan `detil_tugas`). Kontrak submit seleksi (`task_kode`) tidak
  berubah.

## [0.17.0] - 2026-06-23

### Ditambahkan

- **Init DB otomatis saat deploy (tanpa langkah manual)** — image runtime kini
  menyertakan `alembic.ini` + `migrations/`, dan `docker-entrypoint.sh` menjalankan
  `python -m anjab_abk_backend.initdb` (modul baru) sebelum aplikasi naik: `alembic
  upgrade head` lalu seed master data, dengan tunggu-DB-siap. **Idempoten & aman diulang
  tiap `up -d`/restart** — `alembic_version` mencegah migrasi lama dijalankan ulang
  (start kedua dst. no-op) dan seed melompati baris yang sudah ada. Dirancang untuk
  deployment satu instance; multi-replica → jalankan `initdb` sebagai job init terpisah.
- Test `test_init_idempoten_simulasi_up_d` memverifikasi migrasi + seed aman dijalankan
  dua kali (jumlah baris stabil).

### Diperbaiki

- `migrate._resolve_base()` menemukan `alembic.ini`/`migrations/` baik saat dijalankan
  dari repo (pytest, `pythonpath=src`) maupun dari paket ter-install di image runtime
  (`WORKDIR`), dengan override `ANJAB_ALEMBIC_DIR` — memperbaiki keterbatasan sebelumnya
  yang membuat migrasi tak bisa dijalankan dari dalam image runtime.

## [0.16.0] - 2026-06-23

### Ditambahkan

- **Persistensi PostgreSQL** — seam akses data diisi implementasi PostgreSQL nyata
  (SQLAlchemy 2.0 sinkron + psycopg 3): `db.py` (engine, pool, sesi per-request),
  `models.py` (model ORM `TIMESTAMPTZ`/`JSONB`), service `*_sql.py` per domain,
  idempotency & readiness berbasis DB, plus `seed_db.py`. Kontrak API (router, skema,
  Swagger, envelope error) tidak berubah — hanya backend penyimpanan.
- **Mekanisme migrasi schema inkremental (gaya Odoo)** — setiap perubahan struktur
  database menjadi satu berkas revisi Alembic tersendiri di `migrations/versions/`
  (tidak ditumpuk dalam satu berkas). Runner terprogram `migrate.py` (`upgrade`/
  `downgrade`/`current_heads`) dipakai oleh test & tooling.
- **`make migration m="..."`** — autogenerate revisi baru dari selisih model ↔ schema
  memakai PostgreSQL ephemeral (`scripts/make_migration.sh`); berkas baru ditulis ke
  `migrations/versions/` untuk di-review sebelum di-commit.
- **Test penjaga migrasi** (`tests/test_migrations.py`): single-head, integritas graf
  revisi, satu revisi per berkas, kecocokan schema↔model (`compare_metadata`), serta
  round-trip upgrade→downgrade→upgrade. Harness test kini membangun schema lewat
  `alembic upgrade head` (bukan `create_all`) sehingga tiap run ikut memverifikasi migrasi.

### Diperbaiki

- `alembic.ini` post-write hook Ruff memakai `type = exec` (bukan `console_scripts`)
  agar berjalan dengan distribusi biner Ruff yang tidak mendaftarkan entry point.
- `migrations/env.py` menghormati `sqlalchemy.url` yang dipasang lewat Config (mis. DB
  sekali-pakai saat test), hanya membaca dari environment bila kosong.

## [0.15.0] - 2026-06-23

### Diubah (Breaking)

- **TugasPokok M2M ke Jabatan** — `jabatan_id: str` diganti `jabatan_ids: list[str]`
  (wajib, minimal satu). Satu TugasPokok kini dapat terhubung ke beberapa Jabatan.
- **DetilTugas M2M ke Jabatan** — `jabatan_ids: list[str]` ditambahkan (wajib, minimal satu,
  harus subset dari `jabatan_ids` TugasPokok induknya). Validasi subset dijalankan saat buat/perbarui.
- **UraianTugas M2O ke Jabatan eksplisit** — `jabatan_id: str` kini wajib diisi saat membuat
  UraianTugas; nilai harus ada dalam `jabatan_ids` DetilTugas induknya.
- `TugasPokokCreate.jabatan_id` → `TugasPokokCreate.jabatan_ids` (list); `TugasPokokRead` mengembalikan
  `jabatan_ids` (list lengkap) dan `jabatan_kodes` (list kode) sebagai tambahan `jabatan_id` pertama.
- `DetilTugasCreate` dan `DetilTugasRead` kini mengandung `jabatan_ids`.
- `UraianTugasCreate` kini memerlukan `jabatan_id` eksplisit (sebelumnya diwarisi otomatis dari TP).
- Seed data `TugasPokok` dan `UraianTugas` diperbarui konsisten dengan struktur M2M baru.

## [0.14.0] - 2026-06-22

### Diubah (Breaking)

- **Jabatan melekat pada TugasPokok, bukan TiSesi** — `jabatan_id` dipindahkan dari
  `TiSesiCreate/Read/Update` ke `TugasPokokCreate/Read`. `TiSesiCreate` tidak lagi memiliki
  field `jabatan_id` maupun `kategori_jabatan`; `TugasPokokCreate` kini memerlukan `jabatan_id`
  (wajib). `UraianTugas` mewarisi `jabatan_id` secara otomatis dari `TugasPokok` induknya
  (denormalisasi ke `_Record` internal).
- `TiCatalogRead` dan `TiKombinasiRead` dikelompokkan berdasarkan `jabatan_id`
  (menggantikan `kategori_jabatan`).
- `TiKuesionerItemRead.sesi_jabatan_id` menggantikan field `sesi_kategori_jabatan`.
- Uniqueness `TugasPokok` berubah dari `(nama)` menjadi `(nama, jabatan_id)` —
  nama yang sama diperbolehkan untuk jabatan berbeda.
- Seed `TugasPokok` dan `UraianTugas` diperbarui konsisten dengan struktur jabatan baru.

## [0.13.1] - 2026-06-22

### Ditambahkan

- **Batas paginasi dinaikkan** — `pagination_params` kini menerima `limit` hingga 500
  (sebelumnya 100), mendukung halaman admin master data dengan jumlah data besar.
- 4 unit test tambahan: `limit > 100`, dan catalog untuk kombinasi dengan `detil_tugas` kosong.

### Diperbaiki

- `UraianTugasBackedCatalogService._to_catalog()` gagal saat `detil_tugas_id=None`
  (melempar `NotFoundError` karena `self._dt.get(None)`). Kini menghasilkan
  `detil_tugas=None` di `TiCatalogRead` tanpa error.
- `TiCatalogRead.detil_tugas` diubah menjadi `str | None` (sebelumnya `str` wajib).
- Baris deskripsi panjang di `taskinv_catalog.py` dipecah agar lolos ruff E501.

## [0.13.0] - 2026-06-22

### Ditambahkan

- **Sesi TI tanpa unit kerja** — `TiSesiCreate/Read/Update.unit` kini opsional (`str | None`).
  Bila tidak diisi, catalog task mencakup semua unit untuk kategori jabatan sesi tersebut
  (`list_by_kategori()` dipanggil alih-alih `list_by_kombinasi()`).
- `TiCatalogService` Protocol diperluas: `list_by_kategori()` dan `valid_kodes_for_kategori()`
  ditambahkan; endpoint `GET /api/v1/task-inventory/catalog` mendukung query param `unit`
  opsional.
- **SME panel bebas jabatan** — validasi jabatan dihapus dari `add_anggota`; partisipan
  manapun dapat ditambahkan ke panel SME. Cek keanggotaan panel dijalankan saat responden
  didaftarkan ke sesi TI.

## [0.12.0] - 2026-06-22

### Ditambahkan

- **Master data catalog Task Inventory** — tiga model baru dengan CRUD + search lengkap:
  - `TugasPokok` (klaster tugas) — endpoint `GET/POST /api/v1/task-inventory/tugas-pokok`,
    `POST .../search`, `GET/PATCH/DELETE .../tugas-pokok/{tp_id}`.
  - `DetilTugas` (kelompok tugas, M2O ke TugasPokok) — endpoint di `/task-inventory/detil-tugas`.
  - `UraianTugas` (pernyataan tugas, M2O ke TugasPokok **dan** DetilTugas) — endpoint
    di `/task-inventory/uraian-tugas`. Field `detil_tugas_id` bersifat opsional (null) untuk
    task yang tidak masuk detil tugas.
- `seed_catalog_models()` di `taskinv/seed.py` — fungsi idempoten yang meng-seed 77 TugasPokok,
  261 DetilTugas, dan 2738 UraianTugas dari `task_catalog.json` saat startup.
- `UraianTugasBackedCatalogService` di `taskinv/services/catalog.py` — implementasi catalog
  yang baca dari model terpisah (bukan langsung JSON), sehingga perubahan CRUD tercermin.
- Script migrasi `scripts/seed_catalog.py` — panggil REST API untuk mengisi data catalog
  di production. Gunakan: `BASE_URL=... TOKEN=... python scripts/seed_catalog.py`.
- 29 unit test baru di `tests/test_taskinv_master.py` mencakup CRUD + search untuk
  TugasPokok, DetilTugas, dan UraianTugas.

## [0.11.0] - 2026-06-21

### Diubah

- **DCS & WCP: Sesi tidak lagi terikat jabatan** — field `jabatan_id` dihapus dari
  `DcsSesiCreate`, `DcsSesiRead`, `WcpSesiCreate`, dan `WcpSesiRead`. Partisipan
  dengan jabatan apapun dapat di-assign ke sesi yang sama.
- `DcsHasilSesiRead` dan `WcpHasilSesiRead`: field `jabatan_id` dihapus.
- `DcsKuesionerItemRead` dan `WcpKuesionerItemRead`: field `sesi_jabatan_id` dihapus.
- Uniqueness constraint `(jabatan_id, periode)` pada sesi DCS/WCP dihapus — admin
  bebas membuat lebih dari satu sesi per periode.
- `SEARCHABLE_FIELDS` sesi DCS/WCP tidak lagi mengandung `jabatan_id`.
- Semua unit test DCS/WCP diperbarui menyesuaikan skema baru.

## [0.10.0] - 2026-06-21

### Ditambahkan

- **Time Study (Studi Waktu)**: alat ukur baru berupa log harian alokasi waktu kerja per jabatan.
  - Resource `TsSesi` — admin membuat dan mengelola sesi studi waktu per jabatan dan periode.
    Transisi status: `DRAFT → OPEN → CLOSED → ANALYZED`.
  - Resource `TsResponden` — admin men-assign partisipan ke sesi; partisipan wajib di-assign
    sebelum dapat menginput log.
  - Resource `TsLog` — partisipan menginput log harian: waktu masuk, waktu keluar, warna hari
    (GREEN/YELLOW/RED), dan pembagian menit kerja per 6 kategori: Core, Character, Improve,
    Strategic, Admin, Recovery. Kategori CoPilot (AI) dihapus dari instrumen.
  - Validasi: satu log per (responden, tanggal); total menit kategori ≤ durasi kerja + toleransi
    30 menit; `waktu_masuk` harus lebih awal dari `waktu_keluar`.
  - Endpoint `GET /api/v1/time-study/kuesioner/saya` untuk partisipan melihat sesi yang aktif
    beserta jumlah log yang telah diinput.
  - 28 unit test baru pada `test_ts_sesi.py`, `test_ts_responden.py`, `test_ts_log.py`.

## [0.8.0] - 2026-06-21

### Ditambahkan

- **Koordinator SME Panel**: field `koordinator_id` pada resource `SMEPanel` untuk menyimpan
  ID partisipan yang berperan sebagai koordinator panel. Koordinator wajib merupakan anggota
  panel; mengirim `null` pada PATCH menghapus koordinator. Menghapus anggota yang saat ini
  menjadi koordinator juga otomatis menghapus koordinator.
- Empat unit test baru: `test_set_koordinator`, `test_set_koordinator_bukan_anggota`,
  `test_hapus_koordinator`, `test_remove_anggota_clears_koordinator`.

## [0.7.0] - 2026-06-21

### Ditambahkan

- **Batasan 1 WCP per partisipan**: admin tidak dapat mendaftarkan partisipan yang sama ke lebih
  dari satu sesi WCP. Endpoint `POST /api/v1/wcp/sesi/{sesi_id}/responden` kini mengembalikan
  `409 Conflict` apabila `partisipan_id` sudah terdaftar sebagai responden di sesi WCP mana pun.
- Unit test baru: `test_create_responden_duplicate_partisipan_rejected` (409 pada duplikat
  partisipan di lintas sesi WCP).

## [0.6.0] - 2026-06-21

### Ditambahkan

- **Batasan 1 DCS per partisipan**: admin tidak dapat mendaftarkan partisipan yang sama ke lebih
  dari satu sesi DCS. Endpoint `POST /api/v1/dcs/sesi/{sesi_id}/responden` kini mengembalikan
  `409 Conflict` apabila `partisipan_id` sudah terdaftar sebagai responden di sesi DCS mana pun.
- Dua unit test baru: `test_create_responden_partisipan_id_duplikat_ditolak` (409 pada duplikat)
  dan `test_create_responden_tanpa_partisipan_id_boleh_duplikat` (responden anonim tidak
  terkena batasan).

## [0.5.0] - 2026-06-21

### Ditambahkan
- **SME Panel (Subject-Matter Expert Panel)**: instrumen pengumpulan informasi jabatan via
  panel pakar. Mencakup skema, service, dan router `/api/v1/sme-panel/`.

### Diubah
- **DCS & WCP: enrollment berbasis assignment.** Endpoint `GET /kuesioner/saya` untuk DCS
  dan WCP kini hanya mengembalikan sesi yang sudah di-assign admin secara eksplisit
  (record responden dibuat dengan `partisipan_id`). Tidak ada lagi enrollment otomatis
  berdasarkan `jabatan_utama_id`. Setiap alat ukur dapat di-assign secara mandiri.

### Dihapus
- Method `ensure_for_partisipan()` dihapus dari `DcsRespondenService` dan
  `WcpRespondenService` (Protocol & implementasi InMemory).

## [0.4.0] - 2026-06-21

### Diubah
- **Enrollment "Kuesioner Saya" otomatis (computed on-the-fly).** Endpoint
  `/api/v1/dcs/kuesioner/saya` & `/api/v1/wcp/kuesioner/saya` kini menghitung sesi yang
  berlaku untuk partisipan (sesi berstatus `OPEN` dengan `jabatan_id == jabatan_utama_id`
  partisipan) dan membuat record responden secara idempoten — tanpa penugasan manual oleh
  admin. Selaras model "1 deployment = 1 sesi studi, tiap partisipan mengisi semua alat ukur".

### Ditambahkan
- Endpoint `/api/v1/task-inventory/kuesioner/saya` — Task Inventory bersifat **universal**:
  tiap partisipan mengisi SEMUA sesi aktif (`TAHAP1`/`TAHAP2`) tanpa filter jabatan.
- Metode `ensure_for_partisipan` (idempoten, tidak menerapkan batas `max_responden`) pada
  service responden DCS, WCP, dan Task Inventory untuk mendukung enrollment otomatis.

## [0.3.0] - 2026-06-21

### Ditambahkan
- Instrumen **Task Inventory** (Inventori Tugas, standar CalHR 5-komponen) dengan alur 2 tahap:
  Tahap 1 seleksi relevansi task per partisipan, lalu Tahap 2 detailing field CalHR per task
  relevan (dipilih ≥1 partisipan). Status sesi: `DRAFT → TAHAP1 → TAHAP2 → CLOSED → ANALYZED`.
- Catalog master 2.738 task (di-seed dari hasil FGD) per kombinasi Unit × Kategori Jabatan.
- Endpoint `/api/v1/task-inventory/*`: catalog, sesi (CRUD + transisi), responden, seleksi
  Tahap 1, detail Tahap 2, himpunan task terpilih, serta analisis/hasil agregasi (masukan ABK).
- Unittest endpoint Task Inventory: catalog, alur 2 tahap, transisi & guard, agregasi hasil.
- Fitur **Kuesioner Saya**: endpoint `/api/v1/dcs/kuesioner/saya` & `/api/v1/wcp/kuesioner/saya`
  untuk responden melihat kuesioner DCS/WCP yang ditugaskan kepadanya.
- Penautan partisipan pada responden DCS/WCP (`partisipan_id`, `list_by_partisipan`) dan
  pencarian partisipan berdasarkan subject (`get_by_subject`).

## [0.2.0] - 2026-06-20

### Ditambahkan
- Utilitas backup dan restore database PostgreSQL via `make backup` / `make restore` / `make backup-list`.
- Unittest endpoint DCS: list/get/delete responden, list jawaban, hasil sesi, dan analisis dengan K-Index.
- Unittest endpoint WCP: list/get/delete responden, list jawaban, dan hasil sesi.

### Diperbaiki
- Perbaikan pelanggaran `B904` (raise dalam except tanpa `from`) dan `E501` (baris terlalu panjang) di `JwksVerifier`.

## [0.1.0] - 2026-06-12

### Ditambahkan
- Rilis pertama: FastAPI backend dengan modul core (sekolah, partisipan, jabatan), WCP, DCS, dan autentikasi Authentik OIDC.

[Unreleased]: https://github.com/cakrawala-tumbuh/anjab-abk-backend/compare/v0.7.0...HEAD
[0.7.0]: https://github.com/cakrawala-tumbuh/anjab-abk-backend/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/cakrawala-tumbuh/anjab-abk-backend/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/cakrawala-tumbuh/anjab-abk-backend/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/cakrawala-tumbuh/anjab-abk-backend/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/cakrawala-tumbuh/anjab-abk-backend/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/cakrawala-tumbuh/anjab-abk-backend/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/cakrawala-tumbuh/anjab-abk-backend/releases/tag/v0.1.0
