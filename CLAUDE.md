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
- **Setiap operasi GET wajib memasang `dependencies=READ_GUARDS`** (konstanta di
  `dependencies.py`) — **kecuali `/health`, `/ready`, dan `/version`** (`api/v1/system.py`)
  yang memang publik. Tidak ada endpoint baca yang boleh dijangkau tanpa token valid.
  Berlaku juga untuk `POST .../search`: itu operasi *baca* yang mengembalikan data identik
  dengan `GET` pasangannya. Endpoint yang mengembalikan data **per individu** wajib
  menambah guard object-level (`authorize_responden_access` / `authorize_sesi_access` /
  `authorize_opm_sesi_access`) di badan fungsi — token sah saja TIDAK cukup.
  Ditegakkan `tests/test_auth_guards.py` (memindai skema OpenAPI, bukan daftar tulis-tangan):
  operasi GET baru yang lupa diguard langsung menggagalkan test. Lihat entri
  `[2026-07-14] KEAMANAN` di Revisi Desain untuk latar belakangnya.
- ID selalu UUID v4; tidak pakai auto-increment integer.
- Error **selalu** keluar via envelope `errors.py` — jangan `raise HTTPException` mentah.
- Search memakai domain bergaya Odoo (`[field, operator, value]`) — validasi di `services/domain.py`.
- Akses data ke domain lain hanya via seam service `core` — tidak query lintas domain langsung.
- Prefix versi API: `/api/v1/`.
- Autentikasi via JWT Authentik (RS256, JWKS); backend hanya memvalidasi token, tidak menerbitkan.

## Revisi Desain

### [2026-07-15] DCS & WCP: endpoint `reset` — jalur keluar resmi dari `ANALYZED`

Backlog 043. Feedback user (foto, 2026-07-14): "WCP tidak bisa buka sesi" —
instrumen produksi WCP & DCS ter-`ANALYZED` (terminal) oleh **data uji coba** (test
run 2026-07-14, lihat memory `dcs-test-run-2026-07-14.md`/`wcp-test-run-2026-07-14.md`),
tanpa jalan keluar via API untuk memulai pengumpulan data asli. Keputusan produk
(user, 2026-07-15): **Opsi (b)** dari tiga opsi yang disajikan (a: izinkan
`ANALYZED→OPEN` biasa; b: endpoint reset destruktif terpisah; c: tetap terminal,
selesaikan via SQL manual) — dipilih karena memisahkan "buka ulang non-destruktif"
dari "reset destruktif" tanpa mengaburkan makna keduanya.

- **`POST /api/v1/{dcs,wcp}/instrumen/reset`** (admin-only, `_ADMIN_GUARDS`) — dalam
  satu transaksi: hapus SEMUA baris `{Dcs,Wcp}Responden` (jawaban ikut lewat
  `ON DELETE CASCADE`, migrasi `a4aeb5bcbe81`), lalu `status → OPEN`,
  `closed_at → NULL`. **Sah dipanggil dari status APA PUN** (OPEN/CLOSED/ANALYZED) —
  idempoten, berbeda dari `/buka-ulang` yang tetap **hanya** sah `CLOSED→OPEN` dan
  **tidak** menghapus data (tidak berubah). `_VALID_TRANSITIONS` kedua modul
  **tidak diubah** — `reset()` melewati tabel transisi sepenuhnya (method terpisah
  di `{Dcs,Wcp}InstrumenService`, bukan `_transition()`).
- Bulk-delete responden memakai `session.query(Model).delete()` langsung di
  `Sql{Dcs,Wcp}InstrumenService.reset()` (`instrumen_sql.py`) — meniru pola
  `purge_catalog()` (`taskinv/services/catalog_admin.py`): operasi admin bulk
  lintas-baris dalam satu domain. **Sengaja tidak** lewat
  `{Dcs,Wcp}RespondenService.delete()` per-baris — method itu menolak baris
  `sudah_submit=True` (`ValidationAppError`), yang justru SELALU true untuk
  instrumen yang sudah `ANALYZED` (syarat `min_responden` submit sebelum analisis).
- `InMemory{Dcs,Wcp}InstrumenService` **tidak mengimplementasikan** `reset()` —
  konsisten dengan `InMemory{Dcs,Wcp}RespondenService` yang juga tidak
  mengimplementasikan `create_banyak()`: placeholder in-memory tidak punya akses
  lintas-seam ke data responden. Implementasi nyata hanya di seam SQL (yang memang
  satu-satunya dipakai produksi/test, lihat `dependencies.py`).
- `logger.warning("instrumen_reset", extra={"modul": "dcs"|"wcp", "actor": ...})`
  mencatat aktor tiap kali dipanggil (pola sama dengan `paksa=true` di entri
  `[2026-07-12]` dan `catalog_purge` di `taskinv_catalog.py`).
- Tidak ada migrasi Alembic (skema `*_instrumen`/`*_responden` tidak berubah).
  `openapi.json` bertambah 2 operasi baru (`dcs_instrumen_reset`,
  `wcp_instrumen_reset`) — breaking-additive; MCP (`{dcs,wcp}_reset_instrumen`) &
  web app menyusul sebagai item backlog terpisah setelah kontrak ini dirilis.
- Test baru (`test_wcp_instrumen.py`, `test_dcs_instrumen.py`):
  reset dari `ANALYZED` → `OPEN` + responden kosong; idempoten dari `OPEN`; non-admin
  → 403; tanpa token → 401; `buka-ulang` biasa **tetap** 422 dari `ANALYZED` (bukti
  `reset` ≠ `buka-ulang`).
- **Kebutuhan 1 (data-ops)** dari backlog 043 — reset data uji coba DCS produksi
  (3 responden test run 2026-07-14) — dieksekusi terpisah SETELAH endpoint ini
  dirilis, didahului `make backup`. WCP mengikuti pola sama saat/bila dibutuhkan.

### [2026-07-15] TI: hapus tuntas `ai_mode` (`AiMode`) & `dcs_flag` dari kontrak CalHR

Backlog 039, feedback user (foto, 2026-07-14) pada halaman Task Inventory Tahap 3:
dua opsi isian CalHR — **"AI mode"** dan **"Resiko DCS"** — dihapus dari produk.
Keputusan: hapus tuntas dari schema/model/DB, bukan sekadar `exclude`/`disabled` di
UI. Cakupan penuh, semua turunan ikut dibuang:

- **Isian per-entri Tahap 3**: `TiDetailItem.ai_mode`/`.dcs_flag`,
  `TiDetailRead.ai_mode`/`.dcs_flag` (`taskinv/schemas/detail.py`), service
  in-memory + SQL (`services/detail.py`, `services/detail_sql.py`).
- **Nilai standar master (prefill Tahap 3)**: `std_ai_mode`/`std_dcs_flag` di
  `TiCatalogRead` (`schemas/catalog.py`), `UraianTugasCreate`/`Update`/`Read`
  (`schemas/uraian_tugas.py`), service in-memory + SQL
  (`services/uraian_tugas.py`, `services/uraian_tugas_sql.py`,
  `services/catalog.py`).
- **Agregasi hasil**: `TiHasilTaskRead.ai_mode_dist`/`.dcs_flag_count` dan
  `TiTaskTerpilihRead.std_ai_mode`/`.std_dcs_flag` (`schemas/hasil.py`,
  `services/analisis.py`). `va_type`/`va_type_dist`/`std_va_type` **tidak
  disentuh** — hanya `ai_mode`/`dcs_flag` yang dibuang.
- **Enum `AiMode`** (`schemas/calhr.py`) dihapus total, verifikasi 0 importer
  tersisa (`grep -rn AiMode src/`) sebelum dihapus. `VaType`/`SumberBukti`/
  `Kondisi` tetap ada.
- **Model ORM**: `TiDetailModel.ai_mode`/`.dcs_flag`,
  `TiUraianTugasModel.std_ai_mode`/`.std_dcs_flag` dihapus (`models.py`).
- **Migrasi Alembic `fd3dd550aa99`** (dirantai setelah `08b6b999ee05` dari
  backlog 037): `DROP COLUMN` 4 kolom (2 tabel). `ti_detail.ai_mode`/`dcs_flag`
  semula `NOT NULL` tanpa `server_default` — `downgrade()` menambahkan
  `server_default` sementara sebelum `ADD COLUMN` (agar tak gagal di tabel
  berisi), lalu melepas default-nya, konsisten dengan konvensi downgrade
  best-effort repo (`3b10e24fa970`). **Data produksi pada kolom ini hilang
  permanen saat migrasi benar-benar dijalankan** (baris uji coba TI Teranalisis
  YPII kemungkinan terdampak) — konsekuensi produk yang diterima, backup wajib
  sebelum migrasi produksi.
- Test baru `test_detail_ai_mode_dcs_flag_ditolak_sebagai_field_asing`
  (`tests/test_taskinv.py`) menegaskan `422` (`extra="forbid"`) untuk payload
  yang masih menyertakan `ai_mode`/`dcs_flag`.
- Breaking change kontrak API (`openapi.json` berubah). Item 040 (web-app,
  blocked-by 039) meregenerasi tipe setelahnya.

### [2026-07-15] TI: `periode` → `cabang`, hapus `min_responden`/`max_responden`

Backlog 037, feedback user (foto tulisan tangan, 2026-07-14) atas form "Mulai
Analisis Jabatan" Task Inventory. Dua perubahan pada `TiSesi`:

- **`periode` (string bebas `YYYY-MM`) diganti `cabang`** — enum aplikasi 2
  nilai hardcoded, `CabangSesi = Literal["Bandung", "Semarang"]`
  (`taskinv/schemas/sesi.py`, pola sama dengan `StatusSesi`). Bukan FK, bukan
  lookup ke master data. `TiSesiCreate.cabang` **wajib**; `TiSesiRead.cabang`/
  `TiSesiUpdate.cabang` **Optional** — lihat catatan nullable di bawah.
- **`min_responden`/`max_responden` dihapus total** dari `TiSesi` (model,
  semua skema, service SQL + in-memory, search field) — konsisten dengan
  keputusan DCS/WCP di entri `[2026-07-12]` ("1 deployment = 1 studi; tidak
  ada lagi batas atas jumlah responden"). Aturan 422 "panel SME >
  `max_responden`" (backlog 028, entri `[2026-07-14]` di bawah) **dibuang**
  sepenuhnya — auto-populate responden dari SME panel saat create sesi tetap
  ada, sekarang selalu memasukkan SELURUH anggota panel tanpa cap. Cap juga
  dicabut dari lapisan responden TI (`assign_ti_responden_banyak`,
  `SqlTiRespondenService.create`/`assign_banyak`, endpoint
  `POST .../responden` & `.../responden/bulk`) — parameter `max_responden`
  dan cabang `kapasitas_penuh` dihapus dari seluruh jalur TI (string alasan
  `"kapasitas_penuh"` tetap ada di `schemas/common.py` untuk OPM, hanya
  berhenti dipakai TI).
- **Kolom `cabang` di database `nullable=True`, TANPA backfill** (keputusan
  eksplisit, bukan rekomendasi awal backlog yang minta backfill NOT NULL).
  Baris `ti_sesi` produksi lama (2 baris YPII, data uji coba) tetap
  `cabang = NULL` — YPII punya dua cabang (Bandung & Semarang) sehingga nilai
  default tidak bisa ditebak dari data yang ada; admin mengisi manual nanti
  bila perlu, di luar cakupan revisi ini. Migrasi `08b6b999ee05` TIDAK
  menyentuh data produksi (tidak ada `UPDATE`).
- Uniqueness sesi berubah dari `(jabatan_id, periode)` menjadi
  `(jabatan_id, cabang)`.
- Downstream yang membaca `sesi.periode` diganti `sesi.cabang` (bukan sekadar
  dihapus — cabang berguna di UI hasil/kuesioner): `TiHasilSesiRead.periode`
  → `cabang`, `TiKuesionerItemRead.sesi_periode` → `sesi_cabang`
  (`analisis.py`, `api/v1/taskinv_kuesioner.py`), keduanya ikut `CabangSesi |
  None` (echo dari `sesi.cabang` yang Optional).
- Payload lama yang masih mengirim `periode`/`min_responden`/`max_responden`
  ditolak `422` (`TiSesiCreate`/`Update` sudah `extra="forbid"`) — breaking
  change kontrak API, `openapi.json` berubah. Klien (web-app form "Mulai
  Analisis Jabatan", MCP tool `buat_ti_sesi`/`ti_tambah_responden*`)
  menyusul di item 038 + audit MCP terpisah.
- **`OpmSesi` sengaja tidak disentuh** — field `periode`/`min_responden`/
  `max_responden` paralel (`opm/schemas/sesi.py:28,35,38`) tetap ada; scope
  revisi ini murni TI (satu item = satu concern).
- Test regresi baru menegaskan cap benar-benar hilang: panel 11 anggota
  (>batas lama 10) → sesi tetap dibuat, seluruh 11 jadi responden
  (`test_create_sesi_panel_besar_semua_jadi_responden`, `test_taskinv.py`).

### [2026-07-14] OPM: create sesi tidak lagi 409 palsu (`ForeignKeyViolation` yang tersamar)

Risiko yang dicatat sendiri di entri `[2026-07-13]` di bawah ("OPM punya pola bare-FK
identik… catat sebagai risiko bila disentuh di masa depan") **sudah termanifestasi di
produksi**: seluruh alur OPM terblokir total — `POST /api/v1/opm/sesi` untuk jabatan
apa pun ditolak `409 "Sesi OPM untuk jabatan '…' sudah ada."` padahal tabel `opm_sesi`
**kosong** (0 baris, diverifikasi; 2 jabatan berbeda, tetap 409). Pesan itu bohong.

- **`SqlOpmSesiService.create()` kini mem-`flush()` parent lebih dulu** setelah
  `add(rec)`, sebelum menambahkan `OpmRespondenModel` (FK telanjang tanpa
  `relationship()`). Sama persis dengan `SqlTiSesiService.create()`. Flush itu tetap
  lewat `_flush_checked()` — **bukan `self._s.flush()` telanjang seperti TI** — supaya
  unique constraint `jabatan_id` tetap menjadi backstop 409 untuk race dua create
  bersamaan (pre-check langkah 4 lolos di kedua request). `rec.task_links` tidak
  terpengaruh: itu `relationship()`, urutannya memang dijamin.
- **`_flush_checked()` hanya memetakan `UniqueViolation` → `ConflictError` (409).**
  Sebelumnya **semua** `IntegrityError` dipetakan ke "… sudah ada" — dan
  `ForeignKeyViolation` adalah subclass-nya, sehingga bug di atas menyamar jadi konflik
  duplikat yang mustahil dan menyesatkan investigasi selama dua sesi pengujian.
  Pelanggaran integritas lain kini naik apa adanya (500 + stack trace): lebih baik
  gagal berisik daripada berbohong. Perubahan ini **lokal ke OPM** — `_flush_checked`
  di 10 service lain (masing-masing punya salinan sendiri) tidak disentuh; menyeragamkan
  semuanya di luar lingkup revisi ini, tapi patut dilakukan.
- **Koreksi klaim di entri `[2026-07-13]`**: penyebab bug ini selalu lolos unit test
  **bukan** `join_transaction_mode="create_savepoint"`, melainkan **`autoflush`** —
  produksi `autoflush=False` (`db.py`), harness test `autoflush=True` (default). Lihat
  Gotcha. Test regresi `test_create_sesi_tanpa_autoflush_seperti_produksi` memakai
  `db_session.no_autoflush` untuk meniru produksi; diverifikasi **gagal**
  (`ForeignKeyViolation`) bila perbaikan dicabut, sementara seluruh test OPM lain tetap
  hijau — bukti langsung bahwa test biasa buta terhadap kelas bug ini.
- Tidak ada migrasi / perubahan skema Pydantic; `openapi.json` tidak berubah (kontrak
  409 sudah terdokumentasi) — murni perbaikan perilaku runtime.

### [2026-07-14] TI: create sesi menolak panel > `max_responden` (tidak lagi buang diam-diam)

`SqlTiSesiService.create()` auto-populate anggota SME panel jadi responden lewat
`assign_ti_responden_banyak(..., max_responden=data.max_responden)`. Fungsi itu
melewati anggota ke-(N+1) dengan alasan `kapasitas_penuh` dan melaporkannya di
`BulkAssignResult.skipped` — tetapi `create()` **membuang nilai kembalian itu**:
tidak di-log, tidak masuk `TiSesiRead`. Akibatnya sesi tampak sukses (201) padahal
sebagian anggota panel tidak pernah terdaftar; admin lanjut ke Tahap 1→3→analisis
dengan hasil yang bias tanpa jejak apa pun (terjadi di produksi 2026-07-14).

- Kini `create()` **menolak keras** (`ValidationAppError` → 422) bila
  `len(panel.partisipan_ids) > data.max_responden`, dengan pesan yang **sama persis
  bentuknya dengan OPM** (`opm/services/sesi_sql.py::create`, yang sudah benar sejak
  awal): `"Jumlah anggota SME panel (11) melebihi max_responden (10)."` TI & OPM
  konsisten untuk kondisi input yang sama.
- Pengecekan diletakkan **sebelum** `TiSesiModel` dibuat (setelah lookup panel yang
  sudah ada untuk pewarisan koordinator) — tidak ada baris sesi yang terlanjur
  ter-INSERT lalu di-rollback.
- Opsi alternatif "tetap best-effort tapi laporkan `skipped[]` di respons" (menambah
  field ke `TiSesiRead`) **ditolak** — menyisakan ruang salah paham dan mengubah
  kontrak API; "panel besar, responden sedikit" bukan kebutuhan yang pernah diminta.
- Jabatan tanpa panel / panel tanpa anggota → sesi **tetap** dibuat kosong tanpa
  error (perilaku eksisting, sengaja tidak diubah).
- Perubahan **perilaku yang breaking bagi admin**: sesi yang selama ini "berhasil"
  dibuat dari panel >10 anggota kini error. Itu memang tujuannya. Konsekuensi
  lanjutan: sesi TI produksi yang dibuat dari panel besar sebelum revisi ini patut
  dicek ulang (bandingkan jumlah responden vs jumlah anggota panel).
- Tidak ada migrasi / perubahan skema Pydantic; `openapi.json` tidak berubah (422
  sudah terdokumentasi untuk operasi ini).

### [2026-07-14] KEAMANAN: seluruh endpoint baca menuntut token (`READ_GUARDS`)

**32 operasi GET tidak memasang guard autentikasi sama sekali** (hanya
`Depends(rate_limit)`) — dapat dibaca siapa pun **tanpa token**, di produksi.
Diverifikasi lewat `curl` ke produksi, bukan hanya pembacaan kode: `GET /partisipan`
→ 200 + nama/email seluruh pegawai; `GET /{dcs,wcp}/hasil-responden/{id}` → 200 +
hasil psikososial **satu individu**. Pola guard yang benar sebenarnya sudah ada di repo
(`_ADMIN_GUARDS`/`_WRITE_GUARDS`) — hanya tidak pernah diterapkan merata ke operasi baca,
karena otorisasi dipasang **per-operasi di dekorator** dan tidak ada satu pun
`include_router(..., dependencies=...)` di seluruh `src/` yang bisa menjadi jaring pengaman.

- Konstanta baru **`READ_GUARDS`** di `dependencies.py` (bukan per modul router seperti
  `_WRITE_GUARDS`/`_ADMIN_GUARDS`, yang akan terduplikasi di 16 berkas). Dipasang di
  **setiap** GET; `system.py` (`/health`, `/ready`, `/version`) **tidak disentuh**.
- **`POST .../search` (9 endpoint) ikut diguard**, meski secara literal bukan GET:
  `POST /partisipan/search` mengembalikan PII yang sama persis dengan `GET /partisipan`,
  jadi menutup GET saja **tidak** menutup kebocorannya.
- **`GET /{dcs,wcp}/hasil-responden/{id}` mendapat guard object-level** (admin ATAU
  pemilik), memakai ulang `authorize_responden_access()` yang sudah ada — **tidak** dibuat
  helper baru: helper itu sudah persis "admin ATAU partisipan pemilik responden" dan sudah
  dipakai endpoint responden DCS/WCP/OPM/TS. Partisipan tidak boleh membaca hasil
  psikososial rekan kerjanya hanya karena dia login.
- Penjaga: `tests/test_auth_guards.py` memindai **skema OpenAPI** (`app.openapi()["paths"]`),
  BUKAN `app.routes` — router disertakan sebagai `_IncludedRouter` bersarang sehingga
  `app.routes` tidak datar dan filter `isinstance(r, APIRoute)` menghasilkan daftar KOSONG
  (test akan "lulus" secara vakum). Ada test penjaga-bagi-penjaga yang menuntut jumlah rute
  terpindai ≥ 40.
- Guard 401 dievaluasi **sebelum** 404 (dependency FastAPI berjalan sebelum badan fungsi):
  GET tanpa token pada ID yang tidak ada → 401, bukan 404 — keberadaan resource tidak bocor
  ke pemanggil tanpa identitas.
- Tidak ada migrasi / perubahan skema Pydantic. `openapi.json`: hanya `security` + respons
  `401`/`403`/`429`; bentuk request/response tidak berubah → klien (web app, MCP) tidak perlu
  perubahan tipe.
- **Dampak ke test yang sudah ada**: banyak test memakai fixture `anon_client` untuk operasi
  baca (mis. fixture `jabatan_id_tk` di `conftest.py`, katalog TI, sub-skala DCS, dimensi WCP).
  Semuanya dipindahkan ke fixture `client` (ber-token). `anon_client` kini hanya untuk test
  yang memang menegaskan 401/403.

### [2026-07-14] DCS & WCP: `jabatan_label` diresolusi ke nama jabatan (bukan lagi ID mentah)

Ditemukan lewat testing manual di instance produksi YPII: kolom "Jabatan" di
tabel Daftar Responden `/dcs` dan `/wcp`, serta subtext header
`/dcs/hasil-responden/{id}`/`/wcp/hasil-responden/{id}`, menampilkan **ID
internal mentah** (mis. `jbt_4c034eef`) alih-alih nama jabatan. Ini
menyelesaikan catatan "di luar lingkup" yang sengaja ditunda di entri
`[2026-07-12]` di bawah.

- `SqlDcsRespondenService`/`SqlWcpRespondenService` (`{dcs,wcp}/services/
  responden_sql.py`) kini menerima `JabatanService` via DI (pola yang sama
  persis dengan `PartisipanService` yang sudah disuntik ke kelas yang sama) —
  **bukan** query ORM lintas domain langsung seperti pola `OpmRespondenService.
  assign_banyak` (`self._s.get(JabatanModel, ...)` tanpa lewat seam), yang
  tetap dianggap tech debt, bukan preseden.
- Resolusi hanya terjadi di `create_banyak()` (satu-satunya jalur yang dipanggil
  endpoint `POST /api/v1/{dcs,wcp}/responden`): `jabatan_label =
  self._jab.get(partisipan.jabatan_utama_id).nama`. Bila `JabatanService.get()`
  melempar `NotFoundError` (jabatan tidak ditemukan), fallback ke ID mentah +
  `logger.warning` — tidak menggagalkan assign.
- `create()` (single-assign) **sengaja tidak disentuh** — sudah terverifikasi
  tidak dipanggil endpoint apa pun untuk DCS/WCP (kode Protocol yang tidak
  terpakai, peninggalan sebelum revisi `[2026-07-12]`). Bila di masa depan ada
  endpoint baru yang menghidupkan jalur ini, resolusi jabatan perlu ditambahkan
  di titik itu juga.
- Skema TIDAK berubah: `jabatan_label` tetap kolom teks bebas `String(200)`
  (bukan FK) di `DcsRespondenModel`/`WcpRespondenModel` — tidak ada migrasi
  Alembic. `openapi.json` tidak berubah (diverifikasi: diff kosong antara
  sebelum & sesudah perubahan) — murni perubahan nilai runtime + DI internal.
- **Data existing TIDAK dimigrasi otomatis** oleh revisi ini — baris
  `dcs_responden`/`wcp_responden` yang sudah ada (termasuk baris uji coba dari
  sesi testing 2026-07-14 di produksi YPII) tetap menampilkan ID mentah sampai
  ada keputusan eksplisit soal backfill (butuh konfirmasi user sebelum UPDATE
  massal di DB produksi).

### [2026-07-13] Task Inventory: otorisasi endpoint sesi/hasil/tahap2 ditegakkan di backend

Sebelum revisi ini, otorisasi level-sesi Task Inventory murni kosmetik — hanya
digating di frontend (`anjab-abk-web-app`); backend tidak menegakkan apa pun.
Sebagian endpoint **tanpa guard sama sekali** (dapat dibaca tanpa token), yang
lain hanya mensyaratkan token sah tanpa cek peran (`_WRITE_GUARDS`) — partisipan
biasa bisa membaca sesi siapa pun DAN menjalankan seluruh state machine sesi
(termasuk `mulai-tahap3`, yang membekukan himpunan task — **tidak reversibel**).
Bermakna efektif hanya setelah entri `/kuesioner/saya` di bawah (013): sebelum
itu, "punya baris responden di sesi ini" bernilai benar untuk semua partisipan
(auto-enroll universal), sehingga guard lapis 2 tidak menyaring apa pun.

Dua lapis guard baru:

- **Lapis 1 — admin murni** (`dependencies=[Depends(require_admin), Depends(rate_limit)]`,
  konstanta `_ADMIN_GUARDS`, pola persis `taskinv_responden.py`).
- **Lapis 2 — admin ATAU peserta sesi**, lewat helper baru `authorize_sesi_access()`
  (`dependencies.py`, sejajar `authorize_responden_access()`) — dipanggil manual di
  badan endpoint (bukan `dependencies=`) karena butuh objek `sesi` yang sudah di-`get()`.
  Peserta = koordinator sesi (`partisipan.id == sesi.koordinator_id`) **atau**
  partisipan yang punya baris `TiRespondenModel` di sesi itu.

Matriks guard (siapa boleh apa):

| Endpoint | Admin | Koordinator sesi | Anggota panel (responden) | Partisipan lain |
|---|---|---|---|---|
| `GET /sesi`, `POST /sesi/search` | ✅ | ❌ | ❌ | ❌ |
| `POST /sesi` (create), `PATCH /sesi/{id}` | ✅ | ❌ | ❌ | ❌ |
| `POST /sesi/{id}/mulai-tahap1\|2\|3`, `/tutup` | ✅ | ❌ | ❌ | ❌ |
| `POST /sesi/{id}/analisis`, `GET /sesi/{id}/hasil` | ✅ | ❌ | ❌ | ❌ |
| `DELETE /sesi/{id}` (tidak disentuh revisi ini) | ✅ | ❌ | ❌ | ❌ |
| `GET /sesi/{id}` | ✅ | ✅ | ✅ | ❌ |
| `GET /sesi/{id}/tahap2` | ✅ | ✅ | ✅ | ❌ |
| `GET /sesi/{id}/task-terpilih` | ✅ | ✅ | ✅ | ❌ |
| `GET /sesi/{id}/responden` | ✅ | ✅ | ✅ | ❌ |
| `POST /sesi/{id}/tahap2` (submit keputusan, tidak disentuh) | ✅ | ✅ | ❌ | ❌ |

Detail per keputusan:

- **`GET /sesi/{id}/responden`** (`taskinv_responden.py`) direlaksasi dari
  `require_admin` murni menjadi `authorize_sesi_access` — **satu-satunya keputusan
  yang tidak terkunci di spesifikasi backlog, dieksekusi sebagai opsi (a)**.
  Alasan: halaman koordinator web app (`tahap2/[sesi_id]/page.tsx`) memanggil
  endpoint ini untuk menentukan apakah pengunjung adalah anggota panel
  (`isAnggota`); dengan `require_admin` murni, koordinator/anggota non-admin
  SELALU menerima 403 di sana — fitur read-only untuk anggota panel yang
  dimaksud kode itu (`!canEdit` → tampil hanya-baca) sudah lama tidak berfungsi
  secara diam-diam, tanpa laporan. Opsi (b) (biarkan `require_admin`, ubah
  halaman agar tidak memanggilnya) ditolak karena akan menghapus fitur yang
  memang dimaksud ada, bukan memperbaikinya.
- **`POST /sesi/{id}/tahap2` tidak disentuh** — sudah benar (cek koordinator
  eksplisit sejak awal, `taskinv_tahap2.py`).
- Guard 401 dicek **sebelum** 404 pada endpoint lapis 2 (`get_current_principal`
  adalah dependency FastAPI, dievaluasi sebelum badan fungsi) — memanggil
  `GET /sesi/{id}` tanpa token pada ID yang tidak ada mengembalikan 401, bukan 404
  (tidak membocorkan keberadaan sesi ke pemanggil tanpa identitas).
- Tidak ada migrasi/perubahan skema Pydantic — murni pemasangan guard.
  `openapi.json`: hanya penambahan `security`, respons `401`/`403`, dan teks
  `summary`/`description` — bentuk request/response (skema 200) tidak berubah.

### [2026-07-13] OPM: otorisasi endpoint sesi/hasil ditegakkan di backend

Lubang yang sama persis dengan Task Inventory (entri di atas), ditemukan lewat
audit lanjutan atas modul OPM. Berbeda dari TI, OPM **tidak punya konsep
koordinator** (`OpmSesiModel` tidak punya kolom `koordinator_id`, dan tidak ada
satu pun kemunculan kata "koordinator" di `src/anjab_abk_backend/opm/`), jadi
lapis 2 jauh lebih sempit — hanya menyentuh satu endpoint.

Dua lapis guard baru:

- **Lapis 1 — admin murni** (`_ADMIN_GUARDS`, pola sudah ada persis di
  `opm_responden.py`), dipasang di `opm_sesi.py` (baru ditambahkan di modul ini)
  dan dipakai ulang di `opm_hasil.py`.
- **Lapis 2 — admin ATAU responden sesi ini**, lewat helper baru
  `authorize_opm_sesi_access()` (`dependencies.py`, sejajar
  `authorize_sesi_access()` milik TI) — **hanya** `GET /sesi/{id}/task`, satu-
  satunya endpoint sesi-level yang dipanggil halaman pengisian partisipan
  (`opm/isi/[responden_id]`). Peserta = partisipan yang punya baris
  `OpmRespondenModel` di sesi itu — **tidak ada cabang koordinator** (beda dari
  `authorize_sesi_access` TI yang mengecek `sesi.koordinator_id`).

Matriks guard (siapa boleh apa):

| Endpoint | Admin | Responden sesi (anggota panel) | Partisipan lain |
|---|---|---|---|
| `GET /opm/sesi`, `POST /opm/sesi/search` | ✅ | ❌ | ❌ |
| `POST /opm/sesi` (create), `PATCH /opm/sesi/{id}` | ✅ | ❌ | ❌ |
| `GET /opm/sesi/{id}` | ✅ | ❌ | ❌ |
| `POST /sesi/{id}/buka`, `/tutup` | ✅ | ❌ | ❌ |
| `POST /sesi/{id}/analisis`, `GET /sesi/{id}/hasil` | ✅ | ❌ | ❌ |
| `DELETE /sesi/{id}` (tidak disentuh revisi ini — sudah admin-only) | ✅ | ❌ | ❌ |
| `GET /sesi/{id}/task` | ✅ | ✅ | ❌ |
| `GET /sesi/{id}/responden`, `/responden/{id}`, `/responden/{id}/jawaban*` (tidak disentuh — sudah benar) | ✅ | ✅ (pemilik) | ❌ |

Detail per keputusan:

- **`GET /opm/sesi/{id}` (bukan `/task`) sengaja admin-only murni**, berbeda
  dari `GET /task-inventory/sesi/{id}` TI yang memakai lapis 2. Halaman
  partisipan OPM (`opm/isi/[responden_id]`) **tidak pernah memanggil**
  `GET /opm/sesi/{id}` — hanya `/task` — jadi tidak perlu direlaksasi
  (✓ diverifikasi: grep web app).
- Endpoint responden OPM (`opm_responden.py`: list/create/bulk/delete,
  `authorize_responden_access` di get/jawaban) dan `GET /opm/kuesioner/saya`
  **tidak disentuh sama sekali** — sudah benar sejak sebelum revisi ini
  (assignment-based, tidak ada auto-enroll universal seperti bug TI yang
  melahirkan item 013 di atas).
- Guard 401 dicek **sebelum** 404 pada `GET /sesi/{id}/task` (pola sama
  dengan TI) — memanggil endpoint ini tanpa token pada `sesi_id` yang tidak
  ada mengembalikan 401, bukan 404.
- Tidak ada migrasi/perubahan skema Pydantic — murni pemasangan guard.
  `openapi.json`: hanya penambahan `security`, respons `401`/`403`, dan teks
  `summary` — bentuk request/response (skema 200/201/204) tidak berubah.

### [2026-07-13] Task Inventory: `/kuesioner/saya` jadi murni pembacaan (hapus auto-enroll universal)

`GET /task-inventory/kuesioner/saya` sebelumnya mencari **seluruh** sesi
TAHAP1/TAHAP2/TAHAP3 tanpa filter partisipan, lalu memanggil
`ensure_for_partisipan()` yang meng-INSERT baris `TiRespondenModel` per sesi
— membuat endpoint ini bersifat menulis (bukan read-only) dan partisipan bisa
"terdaftar" ke sesi jabatan yang bukan urusannya. Ini sisa desain lama yang
tidak ikut dimigrasikan saat entri `[2026-07-13]` di bawah (auto-populate SME
panel di `SqlTiSesiService.create()`) menambahkan jalur enrollment yang benar
— auto-enroll universal di `/kuesioner/saya` justru **membatalkan**
penyaringan SME panel itu.

- Endpoint diubah jadi murni baca: `list_by_partisipan(par.id)` (pola yang
  sama dengan OPM, `opm_kuesioner.py`) → ambil sesi tiap responden → saring
  status aktif (`TAHAP1|TAHAP2|TAHAP3`). Tidak ada lagi enrollment di waktu
  baca.
- `ensure_for_partisipan()` **dihapus total** dari `TiRespondenService`
  (Protocol, impl in-memory `responden.py`, impl SQL `responden_sql.py`) —
  hanya dipanggil dari satu tempat (`taskinv_kuesioner.py`), tidak ada
  pemakai lain.
- Kontrak `TiKuesionerItemRead` tidak berubah; `openapi.json` tidak berubah
  bentuk skema (hanya deskripsi endpoint).
- Tidak ada migrasi Alembic — `models.py` tidak disentuh.
- **Data lama TIDAK dibersihkan di revisi ini.** Partisipan yang pernah
  membuka halaman kuesioner sejak sesi TI pertama dibuat kemungkinan besar
  punya baris `ti_responden` untuk sesi yang bukan haknya (efek samping bug
  lama). Perubahan ini menghentikan pendarahan, bukan membersihkan data —
  pembersihan butuh konfirmasi eksplisit sebelum dieksekusi (kandidat: baris
  `ti_responden` dengan `tahap1_submit=false` DAN `tahap3_submit=false` DAN
  `partisipan_id` bukan anggota `sme_panel` jabatan sesi tersebut; baris yang
  sudah submit tidak boleh disentuh karena mengubah penyebut unanimity Tahap 2).
- **Koreksi klaim keliru di revisi `[2026-06-21]` di bawah**: baris terakhir
  entri itu menyatakan *"Task Inventory tetap menggunakan flow yang sama
  (assignment manual via tambah-responden)"* — klaim itu **tidak pernah
  benar di kode**. TI baru benar-benar jadi assignment-based lewat revisi ini
  ([2026-07-13], di atas), bukan sejak `[2026-06-21]`.

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

### [2026-07-13] Task Inventory: koordinator sesi diwarisi dari SME panel

`SqlTiSesiService.create()` sekarang mewarisi `koordinator_id` dari
`SmePanel.koordinator_id` jabatan yang sama (panel unik per `jabatan_id`) —
**hanya bila** payload `TiSesiCreate` tidak mengirim `koordinator_id` (payload
menang). Best-effort seperti auto-populate responden yang sudah ada di entri
`[2026-07-13]` di bawah: panel tidak ada / panel tanpa koordinator → sesi tetap
dibuat dengan `koordinator_id = None`, tidak pernah error. Lookup panel
dipindah ke **sebelum** `TiSesiModel` dibuat dan dipakai ulang untuk auto-assign
responden — **satu** query panel, dua keperluan (bukan dua query terpisah).
`InMemoryTiSesiService` (seam in-memory) **tidak** meniru perilaku ini — seam
itu tidak punya akses ke data panel sama sekali. Tidak ada migrasi maupun
perubahan skema Pydantic (`koordinator_id` sudah ada di `TiSesiCreate`/
`TiSesiRead`).

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
  ~~sekadar disalin dari `jabatan_utama_id`, bukan diresolusi ke nama jabatan
  (di luar lingkup revisi ini)~~ **diselesaikan di entri `[2026-07-14]` di
  atas** — kini diresolusi ke nama jabatan via `JabatanService`, dengan
  fallback ke ID mentah bila jabatan tidak ditemukan.
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
- ~~Task Inventory tetap menggunakan flow yang sama (assignment manual via `tambah-responden`).~~
  **KELIRU — koreksi lihat entri `[2026-07-13]` di atas.** Klaim ini tidak pernah benar di
  kode: `GET /task-inventory/kuesioner/saya` sampai revisi `[2026-07-13]` masih memakai
  auto-enroll universal (mendaftarkan partisipan ke SEMUA sesi aktif tanpa filter), bukan
  assignment-based seperti DCS/WCP/OPM. TI baru benar-benar assignment-based sejak revisi
  `[2026-07-13]`.

## Jangan Sentuh

- `migrations/versions/` — migrasi historis yang sudah berjalan; jangan diedit tangan (buat revisi baru).
- `openapi.json` — di-generate `make export-openapi`; jangan edit tangan.
- `src/anjab_abk_backend/security.py` kontrak `TokenVerifier` — seam ini diisi `backend-authentik-skill`, jangan ubah signature-nya.

## Gotcha

- Test butuh env `DATABASE_URL` dan `AUTHENTIK_ISSUER` (lihat `.env.example`); tanpa itu beberapa test bisa gagal senyap.
- `make test` menjalankan linter + unit di dalam Docker — tidak ada artefak di folder project setelah selesai.
- Authentik JWKS di-cache; perubahan kunci di Authentik membutuhkan restart service atau cache TTL habis.
- Endpoint OAuth2 Swagger (`/docs/oauth2-redirect`) wajib didaftarkan di Authentik sebagai Redirect URI.
- **Membuat parent + child ORM baru dalam satu `create()` (mis. sesi + auto-populate anak)**: bila kolom FK anak (`ForeignKey(...)`) TIDAK punya `relationship()` ORM balik ke parent, `session.flush()` gabungan TIDAK menjamin urutan INSERT parent-dulu — flush parent SENDIRI (`self._s.add(parent); self._s.flush()`) sebelum menambah anak, jangan andalkan urutan otomatis. Kasus nyata: `SqlTiSesiService.create()` (entri `[2026-07-13]`) dan `SqlOpmSesiService.create()` (entri `[2026-07-14] OPM`).
- **Kenapa kelas bug di atas lolos test unit: `autoflush`, BUKAN `create_savepoint`.** Produksi memakai `sessionmaker(autoflush=False)` (`db.py`); harness test memakai `Session(...)` dengan `autoflush=True` (default). Di test, autoflush diam-diam mem-flush parent begitu `create()` menjalankan SELECT apa pun setelahnya — parent kebetulan sudah ada saat anak di-INSERT, jadi urutan yang salah tak pernah terlihat. **Test yang menjaga urutan INSERT WAJIB membungkus pemanggilan service dengan `db_session.no_autoflush`** agar meniru produksi (contoh: `test_create_sesi_tanpa_autoflush_seperti_produksi`). Klaim lama bahwa `join_transaction_mode="create_savepoint"` penyebabnya (entri `[2026-07-13]`) **KELIRU** — savepoint bukan yang menyamarkan.

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
