# Changelog

Semua perubahan penting pada proyek ini didokumentasikan di berkas ini.

Format mengacu pada [Keep a Changelog](https://keepachangelog.com/id/1.1.0/),
dan proyek ini menganut [Semantic Versioning](https://semver.org/lang/id/).

## [Unreleased]

## [0.31.0] - 2026-07-13

### Ditambahkan

- **Penugasan massal (bulk) untuk TS, TI, OPM + auto-populate SME panel di TI.**
  Menyusul pola bulk yang sudah ada di WCP/DCS, tapi bersifat **idempoten**
  (skip-on-conflict), bukan atomik all-or-nothing — cocok untuk TS/TI/OPM
  yang tidak seperti WCP/DCS punya endpoint single yang tetap dipertahankan.
  - `POST /api/v1/time-study/penugasan/bulk` — body `partisipan_ids: list[str]`
    (min 1), `aktif`, `catatan`. Skip `sudah_terdaftar`/`duplikat_input`.
  - `POST /api/v1/task-inventory/sesi/{sesi_id}/responden/bulk` — body
    `partisipan_ids: list[str]`. Skip `sudah_terdaftar`/`duplikat_input`/
    `bukan_anggota_sme_panel`/`kapasitas_penuh`. `nama` responden bulk/
    auto-populate diresolusi dari `PartisipanModel` (bukan anonim).
  - `POST /api/v1/opm/sesi/{sesi_id}/responden/bulk` — sama seperti TI;
    `nama`/`jabatan_label` diresolusi otomatis dari `PartisipanModel`/
    `JabatanModel` (tidak perlu dikirim di payload, beda dari endpoint single).
  - Response envelope baru `BulkAssignResult[T]` (`schemas/common.py`):
    `{created: T[], skipped: [{partisipan_id, alasan}]}`.
  - **TI: sesi baru otomatis mendapat responden dari SME panel jabatannya**
    (bila panel ada & punya anggota) — meniru pola auto-populate yang sudah
    ada di OPM. Sesi untuk jabatan tanpa panel/panel kosong tetap dibuat
    kosong seperti sebelumnya.
  - Endpoint single (manual) yang sudah ada — `POST /time-study/penugasan`,
    `POST .../task-inventory/sesi/{id}/responden`,
    `POST .../opm/sesi/{id}/responden` — **tidak berubah** kontraknya.
- **`koordinator_id` sesi Task Inventory diwarisi dari `SmePanel.koordinator_id`
  jabatannya saat sesi dibuat** (`SqlTiSesiService.create()`), bila payload
  `POST /api/v1/task-inventory/sesi` **tidak** mengirim `koordinator_id` secara
  eksplisit — payload tetap menang bila dikirim. Best-effort seperti
  auto-populate responden: panel tidak ada / panel tanpa koordinator → sesi
  tetap dibuat dengan `koordinator_id = null`, tidak pernah error. Sebelumnya
  admin harus menetapkan koordinator manual lewat `PATCH` setelah sesi dibuat;
  ditemukan lewat simulasi E2E TI di deployment YPII — sesi baru selalu
  menampilkan "Koordinator: Belum ditentukan" walau koordinator sudah
  ditetapkan di Master Data → SME Panel. Panel di-query **satu kali** di
  `create()` (dipakai untuk koordinator maupun auto-assign responden — tidak
  ada query ganda). Tidak ada migrasi, tidak ada perubahan skema Pydantic —
  murni perbaikan urutan logika. Seam in-memory (`InMemoryTiSesiService`)
  sengaja tidak mengikuti perilaku ini (tidak punya akses ke data panel).

### Diperbaiki

- **`SqlTiSesiService.create()`: urutan flush sesi vs. auto-populate responden.**
  Ditemukan lewat E2E langsung (bukan unit test — lolos begitu saja di harness
  test karena beda perilaku sesi transaksi), lalu direproduksi manual: baris
  sesi Task Inventory harus di-`flush()` sendiri sebelum insert responden
  auto-populate, karena `TiRespondenModel.sesi_id` adalah FK murni tanpa
  `relationship()` ORM balik ke `TiSesiModel` — tanpa flush eksplisit,
  SQLAlchemy tidak menjamin urutan INSERT saat flush gabungan, sehingga bisa
  mencoba insert responden sebelum baris sesi ada (`ForeignKeyViolation`,
  gagal 500). Lihat catatan lengkap di `CLAUDE.md` (Revisi Desain & Gotcha).

## [0.29.0] - 2026-07-13

### Diubah (BREAKING)

- **DCS & WCP: hapus entitas sesi, ganti pola singleton + penugasan langsung.**
  Meniru pola yang sudah dipakai Time Study (`TsPenugasanModel`, lihat revisi
  `0a58616358f4`). Alasan: 1 deployment backend = 1 studi (sudah menjadi
  keputusan produk sejak beberapa revisi lalu) — entitas sesi per-instrumen
  jadi lapisan tak berguna yang hanya menambah kerumitan operasional (admin
  harus buat & buka sesi dulu sebelum bisa assign responden).
  - Tabel `dcs_sesi`/`wcp_sesi` **dihapus total**, diganti `dcs_instrumen`/
    `wcp_instrumen` — **singleton**, satu baris tetap (`id='dcs'`/`id='wcp'`)
    dibuat oleh migrasi. Tidak ada endpoint create/delete instrumen.
  - Status instrumen `OPEN → CLOSED → ANALYZED` (tanpa `DRAFT` — instrumen
    sudah `OPEN` sejak migrasi). Reopen `CLOSED → OPEN` diizinkan selama
    belum `ANALYZED`.
  - Kolom `periode` dan `max_responden` **dihapus** (redundan — 1 deployment
    = 1 studi; tidak ada lagi batas atas jumlah responden, hanya
    `min_responden` sebagai cutoff analisis).
  - `dcs_responden`/`wcp_responden` kehilangan kolom `sesi_id`; `partisipan_id`
    kini **unik** lintas seluruh responden (`UNIQUE`, PostgreSQL mengizinkan
    banyak `NULL`).
  - **Endpoint dihapus total** (tanpa deprecation): seluruh
    `.../sesi/{sesi_id}/...` DCS & WCP, termasuk create/update/delete/search
    sesi dan parameter query `wcp_sesi_id` pada analisis K-Index DCS.
  - **Endpoint baru**: `GET/PATCH /dcs/instrumen` (atau `/wcp/instrumen`),
    `POST /dcs/instrumen/tutup`, `POST /dcs/instrumen/buka-ulang`,
    `GET/POST /dcs/responden` (bulk — body `partisipan_ids: list[str]`,
    minimal 1), `GET/DELETE /dcs/responden/{id}`, `PUT/POST/GET
    /dcs/responden/{id}/jawaban*`, `POST /dcs/analisis`, `GET /dcs/hasil`,
    `GET /dcs/hasil-responden/{id}` (idem WCP).
  - K-Index DCS kini selalu dihitung otomatis dari instrumen WCP (tanpa
    parameter); `wcp_risk`/`k_index` bernilai `null` hanya bila WCP belum
    punya responden ber-submit.
  - **Deviasi dari desain awal (perlu diverifikasi konsumen API)**:
    `DcsRespondenCreate`/`WcpRespondenCreate` HANYA menerima `partisipan_ids`
    (bukan lagi `nama`/`jabatan_label` per baris) — assign massal kini murni
    berbasis partisipan yang sudah terdaftar di `core.partisipan` (validasi
    lewat `PartisipanService.get()`, 404 bila `partisipan_id` tidak ada).
    `nama` & `jabatan_label` di baris responden diisi OTOMATIS dari data
    partisipan (`partisipan.nama`, `partisipan.jabatan_utama_id` — kolom
    `jabatan_label` TETAP teks bebas, bukan FK, sesuai keputusan yang
    dikunci; nilainya sekadar disalin, bukan diresolusi ke nama jabatan).
    Sebagai konsekuensi, pembuatan responden ANONIM (tanpa `partisipan_id`)
    tidak lagi didukung lewat endpoint publik manapun untuk DCS/WCP.
  - Migrasi (`3b10e24fa970`, satu berkas untuk DCS & WCP) menolak jalan
    (`RuntimeError`) bila ditemukan >1 sesi DCS/WCP yang MASING-MASING
    punya ≥1 responden — instrumen singleton tak bisa mewakili lebih dari
    satu kumpulan responden. `min_responden`/`catatan`/status disalin dari
    sesi ber-responden bila ada (default dipakai bila tidak ada).
  - Downgrade migrasi best-effort (struktur tabel lama dipulihkan kosong,
    data tidak direkonstruksi) — mengikuti konvensi `0a58616358f4`.
  - TI dan OPM (sesi jabatan) **tidak disentuh** oleh revisi ini.

## [0.28.0] - 2026-07-12

### Ditambahkan

- **Endpoint admin purge & reseed katalog master Task Inventory** —
  `POST /task-inventory/catalog/purge` dan `POST /task-inventory/catalog/reseed`.
  Menjadikan purge+reseed katalog (`ti_uraian_tugas`/`ti_tugas_pokok`/
  `ti_detil_tugas`) sebagai fitur admin resmi via API, menggantikan
  ketergantungan pada `scripts/purge_task_catalog.py` yang butuh akses
  `DATABASE_URL` produksi langsung. `purge` ditolak (409, hard-blocked tanpa
  flag override) bila masih ada ≥1 sesi Task Inventory — `ti_seleksi`/
  `ti_tahap2`/`ti_detail` merujuk katalog lewat `task_kode` string (bukan FK),
  sehingga purge saat ada sesi berjalan akan merusak data transaksi.
  `seed_catalog_models` kini mengembalikan `SeedSummary` (jumlah baris
  jabatan/tugas_pokok/detil_tugas/uraian_tugas yang di-seed) alih-alih `None`.

## [0.27.0] - 2026-07-12

### Ditambahkan

- **Nilai standar CalHR di master catalog Task Inventory.** `ti_uraian_tugas`
  mendapat 9 kolom `std_*` (`std_sumber_bukti`, `std_kondisi`,
  `std_frekuensi_teks`, `std_durasi_per_kali`, `std_jam_per_minggu`,
  `std_peak4w_hours`, `std_ai_mode`, `std_va_type`, `std_dcs_flag`) — dipakai
  untuk mem-prefill isian partisipan di Tahap 3 sehingga cukup menyatakan
  setuju alih-alih mengisi dari nol. `ti_detail` mendapat `setuju_standar`
  (boolean, default `true`) yang merekam apakah partisipan menerima nilai
  standar apa adanya. Literal `SumberBukti`/`Kondisi`/`AiMode`/`VaType`
  dipindah ke modul bersama `taskinv/schemas/calhr.py`.
- **Master catalog Task Inventory diganti total dari Task Bank v2_19**
  (`Task_Bank_Complete_AllRoles_v2_19.xlsx`, sheet `05_Raw_Task_Migration`,
  1.140 baris setelah baris `Final_Decision=Retire` dibuang) — menggantikan
  katalog lama 2.738 baris (hasil FGD, tanpa nilai standar CalHR). Katalog
  baru membawa nilai standar CalHR penuh untuk kelima komponen yang punya
  sumber di Excel. `unit` diisi konstanta `"ALL"` (kolom `Jenjang` sumber
  92% bernilai `ALL` dan tidak dipakai alur mana pun). Skrip ekstraksi
  (`extract_task_bank.py`, di repo induk) merekonstruksi 265 baris kolom
  `Baseline_Peak` yang terkontaminasi nilai frekuensi (validasi silang
  5-fold 85%) dan menyalin 2 baris `Perlu Validasi` dari induk kanonik yang
  ditunjuk eksplisit oleh `Reviewer_Notes`.
- `scripts/purge_task_catalog.py` — hapus seluruh master catalog Task
  Inventory (`ti_uraian_tugas`, `ti_detil_tugas`, `ti_tugas_pokok` + baris
  link M2M via `ON DELETE CASCADE`) sebelum re-seed dari `task_catalog.json`
  baru. Seeder bersifat insert-if-absent — ganti-total katalog butuh purge
  eksplisit, tidak otomatis membackfill/menghapus baris lama.

### Diubah

- **BREAKING**: `std_durasi_per_kali` (master) berubah tipe dari `Integer`
  ke `String(100)` — nilai standar durasi di Task Bank v2_19 berupa teks
  bebas (mis. `"Bervariasi"`, `"<2 jam"`), bukan angka menit. Kolom jawaban
  responden `ti_detail.durasi_per_kali` (Integer, dipakai hitung beban
  kerja ABK) **tidak berubah**.
- `VaType` diperluas dari 3 jadi 5 nilai: tambah `Context-Dependent` dan
  `Needs Validation` (26% baris Task Bank v2_19 berstatus kurasi belum
  diputuskan, bukan nilai yang bisa ditebak — SME yang memutuskan kategori
  VA finalnya di Tahap 3). Dipakai bersama oleh nilai standar master dan
  jawaban responden; konsekuensinya responden kini bisa memilih kedua nilai
  itu sebagai jawaban akhir.

### Diperbaiki

- **Bug seeder tak terlaporkan**: `seed_catalog_models` tidak pernah
  meneruskan field `std_*` dari `task_catalog.json` ke `UraianTugasCreate` —
  kolom `std_*` di DB selalu `NULL` walau JSON sumbernya berisi. Ditambal +
  unit test penjaga regresi.

## [0.26.0] - 2026-07-12

### Ditambahkan

- **Force-delete sesi admin via `?paksa=true`.** `DELETE .../{dcs|wcp|opm|taskinv}
  /sesi/{sesi_id}` kini menerima query param opsional `paksa` — admin dapat
  menghapus sesi non-DRAFT beserta seluruh responden & jawabannya (permanen).
  Tanpa `paksa`, perilaku lama tetap berlaku (422, hanya DRAFT yang bisa dihapus).

### Diperbaiki

- **FK `ON DELETE CASCADE` di 12 kolom `sesi_id`/`responden_id`** (DCS, WCP, OPM,
  Task Inventory) — dulu `String(40)` tanpa constraint, sehingga menghapus sesi
  atau responden meninggalkan baris anak yatim yang tak terjangkau API mana pun.
  Migrasi membersihkan baris yatim yang sudah ada sebelum membuat FK. Menambal
  bug tak terlaporkan: menghapus responden dulu tidak ikut menghapus jawabannya.

## [0.25.1] - 2026-07-12

### Diperbaiki

- **`DELETE` sesi (DCS/OPM/WCP/Task Inventory) kini hanya admin.** Keempat
  endpoint `DELETE /{dcs|opm|wcp|taskinv}/sesi/{sesi_id}` sebelumnya memakai
  guard `_WRITE_GUARDS` (siapapun yang login boleh menghapus), berbeda dari
  endpoint `DELETE` responden/penugasan yang sudah dibatasi admin. Menghapus
  sebuah Sesi men-cascade hapus seluruh responden & jawaban di bawahnya,
  sehingga celah ini kini ditutup: keempat endpoint memakai `_ADMIN_GUARDS`
  (`require_admin`) dengan response `403` bila bukan admin.

## [0.25.0] - 2026-07-08

### Ditambahkan

- **Simpan draft sebelum submit final — DCS, WCP, OPM, Task Inventory Tahap 1 & 3.**
  Kelima instrumen ini tadinya "submit sekali jadi" (satu `POST` bulk yang wajib
  lengkap dan langsung mengunci status). Sekarang partisipan dapat menyimpan
  progres bertahap sebelum finalisasi:
  - `PUT .../jawaban` (atau `.../seleksi`, `.../detail`) — upsert payload **parsial**
    (boleh 0..N item); ditolak (422) bila responden sudah submit final. Task
    Inventory Tahap 1 (seleksi) memakai semantik **full-replace** (representasi
    alami untuk "pilihan saat ini" sebuah checkbox set); DCS/WCP/OPM/Tahap 3
    (detail) memakai upsert per item.
  - `POST .../jawaban/submit` (atau `.../seleksi/submit`, `.../detail/submit`) —
    endpoint baru tanpa body: memvalidasi kelengkapan dari baris yang sudah
    tersimpan di DB, lalu menandai flag submit + timestamp.

### Diubah (Breaking)

- `POST .../jawaban`, `POST .../seleksi`, `POST .../detail` (submit sekali-jadi,
  wajib lengkap) **dihapus** — diganti pasangan `PUT` (draft) + `POST .../submit`
  (finalisasi) di atas. Skema request `*BulkCreate`/`*Submit` diganti
  `*Upsert`/`*DraftSave` (tanpa syarat kelengkapan; validasi kelengkapan pindah ke
  endpoint submit).

## [0.24.0] - 2026-07-04

### Diperbaiki

- **Keamanan: Broken Object-Level Authorization (BOLA/IDOR) pada endpoint responden
  Task Inventory, DCS, WCP, OPM, dan Time Study.** Partisipan sebelumnya dapat melihat
  atau mengubah data responden/penugasan milik partisipan lain hanya dengan menebak
  `responden_id`/`penugasan_id` — beberapa endpoint GET bahkan tidak mewajibkan token
  sama sekali.
  - Helper baru `authorize_responden_access` di `dependencies.py`: admin selalu
    diizinkan; selain itu hanya partisipan pemilik record yang diizinkan, lainnya
    ditolak `403`.
  - Diterapkan pada endpoint per-responden: `GET/POST` seleksi & detail Tahap 1/3
    Task Inventory, `GET/POST` jawaban DCS/WCP/OPM, dan `GET/POST/PATCH` log Time Study.
  - `GET /time-study/penugasan/{id}/log/{log_id}` & `PATCH` kini juga memverifikasi
    `log_id` benar-benar milik `penugasan_id` di path (mencegah kombinasi silang).

### Diubah (Breaking)

- Endpoint manajemen responden/penugasan (`list`, `create`, `delete` responden Task
  Inventory/DCS/WCP/OPM; `list`, `create`, `update`, `delete` penugasan Time Study)
  kini **admin-only** — sebelumnya dapat diakses oleh partisipan mana pun yang
  terautentikasi (atau, untuk beberapa endpoint GET, tanpa autentikasi sama sekali).

## [0.23.0] - 2026-07-04

### Diubah

- **BREAKING: Time Study tanpa sesi — penugasan berbasis partisipan langsung.**
  - Model `TsSesiModel`/`TsRespondenModel` dihapus; diganti `TsPenugasanModel` (satu
    penugasan per partisipan, membawa flag `aktif` sebagai pengganti state machine
    `DRAFT→OPEN→CLOSED→ANALYZED`).
  - `TsLogModel.responden_id` diganti `partisipan_id`; constraint unik berubah dari
    `(responden_id, tanggal)` menjadi `(partisipan_id, tanggal)`.
  - Endpoint dirombak: `/api/v1/time-study/sesi` dan
    `/api/v1/time-study/sesi/{sesi_id}/responden` diganti
    `/api/v1/time-study/penugasan` (CRUD); `/api/v1/time-study/responden/{responden_id}/log`
    menjadi `/api/v1/time-study/penugasan/{penugasan_id}/log`.
  - `GET /api/v1/time-study/kuesioner/saya` kini mengembalikan penugasan aktif milik
    partisipan (bukan daftar sesi berstatus OPEN); field `TsKuesionerItemRead` diringkas
    menjadi `{id, aktif, jumlah_log, created_at}`.
  - Pencatatan/pembaruan log ditolak (422) selama penugasan berstatus nonaktif.
  - Migrasi Alembic membackfill `ts_penugasan` dari `ts_responden` ber-`partisipan_id`
    dan mengaitkan ulang `ts_log` ke `partisipan_id`; log dari responden anonim
    (tanpa `partisipan_id`) dihapus karena tak dapat dipetakan.

## [0.22.0] - 2026-07-02

### Ditambahkan

- **Instrumen OPM (Rating Tugas — Importance/Frequency/Criticality)** — instrumen baru untuk
  menilai task hasil Task Inventory pada 3 dimensi skala 1–5 (Importance, Frequency, Criticality).
  - Model baru: `OpmSesiModel` (satu sesi per jabatan, wajib punya SME panel), `OpmSesiTaskModel`
    (snapshot task dari sesi TI yang sudah dibekukan), `OpmRespondenModel` (auto-terisi dari
    anggota SME panel), `OpmJawabanModel`.
  - Package `opm/` (schemas + services) dan router baru `api/v1/opm_sesi.py`, `opm_responden.py`,
    `opm_hasil.py`, `opm_kuesioner.py` — mengikuti pola instrumen WCP/DCS: alur status
    `DRAFT → OPEN → CLOSED → ANALYZED`, transisi, kuesioner-saya, dan analisis hasil
    (mean/SD per dimensi + flag `selection_essential`/`workload_essential` dari mean, plus
    proporsi rater per formula individual).
  - Sesi OPM membekukan task via snapshot dari sesi Task Inventory (`ti_sesi_id`) yang sudah
    `task_frozen=True`, sehingga tidak lagi bergantung pada TI setelah dibuat.
  - Migrasi Alembic baru untuk 4 tabel `opm_*`.

## [0.21.6] - 2026-06-26

### Ditambahkan

- **Field `sesi_jabatan_nama` di `TiKuesionerItemRead`** — endpoint `GET /task-inventory/kuesioner/saya`
  kini mengembalikan nama jabatan (`sesi_jabatan_nama`) sehingga frontend dapat menampilkan
  nama jabatan yang terbaca manusia, bukan kode ID jabatan, pada halaman kuesioner partisipan.

## [0.21.5] - 2026-06-26

### Ditambahkan

- **Field `is_koordinator` di `TiKuesionerItemRead`** — endpoint `GET /task-inventory/kuesioner/saya`
  kini mengembalikan `is_koordinator: bool` yang bernilai `true` jika pengguna saat ini
  adalah koordinator SME panel untuk sesi tersebut. Digunakan frontend untuk menampilkan
  tombol "Review Koordinator" di halaman kuesioner partisipan.

## [0.21.4] - 2026-06-26

### Ditambahkan

- **Endpoint `GET /api/v1/partisipan/saya`** — mengembalikan data partisipan pengguna
  yang sedang login berdasarkan JWT Bearer. Menggunakan `get_by_subject` untuk lookup
  partisipan dari `principal.subject` (sub JWT = email). Merespons 404 jika partisipan
  tidak ditemukan.

## [0.21.3] - 2026-06-26

### Diperbaiki

- **Koordinator Tahap 2 selalu mendapat 403** — pemeriksaan otorisasi di endpoint
  `POST /api/v1/task-inventory/sesi/{sesi_id}/tahap2` membandingkan `principal.subject`
  (UUID Authentik) langsung dengan `sesi.koordinator_id` (format `par_XXXX`), sehingga
  selalu tidak cocok. Kini endpoint melakukan lookup partisipan via `get_by_subject`
  terlebih dahulu, lalu membandingkan `par.id` dengan `koordinator_id`.

## [0.21.2] - 2026-06-26

### Diperbaiki

- **`koordinator_id` sesi TI dapat diperbarui di luar status DRAFT** — guard update
  sesi sebelumnya memblokir seluruh field saat status bukan DRAFT, termasuk
  `koordinator_id`. Kini `koordinator_id` dapat diperbarui di status apapun;
  field lain tetap hanya bisa diubah saat DRAFT.

## [0.21.1] - 2026-06-25

### Diperbaiki

- **Tahap 2 Task Inventory: submit keputusan hanya bisa dilakukan admin** — endpoint
  `POST /api/v1/task-inventory/sesi/{sesi_id}/tahap2` tidak memiliki pemeriksaan
  otorisasi koordinator. Kini endpoint menolak permintaan dengan 403 jika pengirim
  bukan admin dan bukan koordinator SME panel yang tercatat di `sesi.koordinator_id`.

## [0.21.0] - 2026-06-25

### Diubah

- **`DcsKuesionerItemRead` & `WcpKuesionerItemRead`: ganti `jabatan_label` → `sesi_catatan`** —
  endpoint `/kuesioner/saya` DCS dan WCP tidak lagi mengekspos `jabatan_label` responden ke
  partisipan. Sebagai gantinya, field `sesi_catatan` (catatan sesi, nullable) dikembalikan
  sebagai pengenal sesi. `jabatan_label` tetap ada di `DcsRespondenRead` dan `WcpRespondenRead`
  untuk kebutuhan tampilan admin.

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
