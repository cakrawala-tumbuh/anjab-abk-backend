# Changelog

Semua perubahan penting pada proyek ini didokumentasikan di berkas ini.

Format mengacu pada [Keep a Changelog](https://keepachangelog.com/id/1.1.0/),
dan proyek ini menganut [Semantic Versioning](https://semver.org/lang/id/).

## [Unreleased]

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
