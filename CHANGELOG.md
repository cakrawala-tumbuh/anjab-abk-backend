# Changelog

Semua perubahan penting pada proyek ini didokumentasikan di berkas ini.

Format mengacu pada [Keep a Changelog](https://keepachangelog.com/id/1.1.0/),
dan proyek ini menganut [Semantic Versioning](https://semver.org/lang/id/).

## [Unreleased]

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

[Unreleased]: https://github.com/cakrawala-tumbuh/anjab-abk-backend/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/cakrawala-tumbuh/anjab-abk-backend/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/cakrawala-tumbuh/anjab-abk-backend/releases/tag/v0.1.0
