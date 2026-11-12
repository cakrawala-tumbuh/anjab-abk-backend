# Changelog

Semua perubahan penting pada proyek ini didokumentasikan di berkas ini.

Format mengacu pada [Keep a Changelog](https://keepachangelog.com/id/1.1.0/),
dan proyek ini menganut [Semantic Versioning](https://semver.org/lang/id/).

## [Unreleased]

### Ditambahkan

- **Penerima jamak dan kesiapan per periode pada alternatif redesain** (backlog #133, revisi `91d5ea3c7153`): tabel `redesain_alternatif_penerima` (backfill dari `pihak_penerima_jabatan_id`; kolom lama dipertahankan) dan `redesain_kesiapan` (append-only; delta asal/penerima/organisasi, `NOT_ESTIMABLE` tersimpan null bukan nol). Rute `tim-kajian` di `/api/v1/redesain/alternatif/{id}`: `GET/POST /penerima` (409 `PENERIMA_GANDA`), `POST /kesiapan` (422 `PENERIMA_BUKAN_MILIK_ALTERNATIF`; `syarat` wajib bila CONDITIONAL, `alasan_hold` wajib bila HOLD), `GET /kesiapan?periode=2026/27` (matriks dari penilaian terakhir + `status_opsi`; HOLD bila ada penerima material HOLD atau belum dinilai, atau tanpa penerima). Fungsi murni `hitung_status_opsi` disiapkan untuk ChangeDecision (#134) dan P06/P07 (#135).
- **Cerita pra-bank Task Inventory dan log paparan bank tugas** (backlog #131, revisi `a1c5e7b93d20`): saklar baru `FEATURE_PREBANK_FREEZE` (anggota `FiturKode.PREBANK_FREEZE`, bawaan mati; `GET /api/v1/system/fitur` kini memuat enam kode). Tabel `ti_cerita_prabank` (satu cerita per responden, `frozen_at`) dan `ti_paparan_event` (append-only; trigger menolak `UPDATE`, memakai ulang `narasi_tolak_ubah()`). Empat rute di `/api/v1/task-inventory/sesi/responden/{responden_id}` (admin atau pemilik responden; saklar mati 409 `feature_disabled`): `PUT /cerita-prabank` (409 `CERITA_SUDAH_DIKUNCI` bila sudah beku), `POST /cerita-prabank/bekukan` (idempoten; 422 `CERITA_KOSONG`), `POST /paparan` (201; `status_saat_paparan` `LOCKED_PRE_EXPOSURE` bila cerita sudah beku, selain itu `EXPOSED`; waktu dari server, field asing 422), `GET /prabank` (`cerita`, `frozen_at`, `first_exposed_at`, `exposure_state`). Saat saklar hidup, `PUT .../seleksi` sebelum ada paparan 409 `PAPARAN_BELUM_TERCATAT`; saklar mati tidak mengubah perilaku seleksi. Seam `TiPrabankService.status_paparan(responden_id)` disiapkan untuk antrean narasi.
- **Status paparan F2 di antrean narasi** (backlog #132): `paparan` pada `GET /api/v1/narasi/antrean` (field baru per baris, plus `assignment_ref`) dan `GET /api/v1/narasi/antrean/{narasi_id}` kini dihitung saat baca. F1 dan jenis lain `TIDAK_BERLAKU`; F2 yang `assignment_ref`-nya id responden TI memakai status responden (`BELUM_TERPAPAR`, `LOCKED_PRE_EXPOSURE`, `EXPOSED`); F2 tanpa pasangan `TIDAK_DIKETAHUI`. Daftar memakai satu kueri batch (`TiPrabankService.status_paparan_banyak`). Tanpa migrasi.

## [0.50.0] - 2026-11-10

### Ditambahkan

- **Aksi Terapkan kandidat P11 menjadi konteks redesain** (backlog #128, revisi `8e8950b14821`): `POST /api/v1/ai/usulan/{usulan_id}/terapkan-konteks` (201 `KonteksRead`; `tim-kajian`; rate-limit; `Idempotency-Key`; badan `TerapkanKonteks` = `indeks_kandidat` (>= 0), `kode` (pola `K-NN`), `gelombang`, dan opsional `tema`/`ruang_dugaan`/`sumber_draft`/`batas_pemeriksaan` yang menimpa isian kandidat; field asing 422). Membuat SATU konteks baru `aktif=true` dari `isi.konteks_candidates[indeks_kandidat]` dan mencatat riwayat `create`; putusan tetap tidak menyentuh tabel domain. Usulan tak ada 404; fungsi bukan P11 atau sasaran bukan `REDESAIN_KONTEKS` 422 `USULAN_BUKAN_P11`; putusan terakhir bukan `APPROVE`/`REVISE` 409 `USULAN_BELUM_DITERIMA`; indeks di luar rentang atau `isi` null 422 `KANDIDAT_TAK_ADA`; putusan terakhir `REVISE` tanpa keempat isian 422 `ISIAN_REVISI_WAJIB`; kandidat sudah diterapkan 409 `KANDIDAT_SUDAH_DITERAPKAN` (`details[0].msg` = id konteks yang ada); kode konteks dipakai 409 `conflict`; isian gabungan tak sah (mis. `tema` > 200) 422 `validation_error`. Kolom baru `redesain_konteks.ai_usulan_id` (FK `ai_usulan.id` `ON DELETE RESTRICT`) dan `ai_kandidat_indeks` (SMALLINT) dengan CHECK keduanya null atau keduanya terisi dan UNIQUE pasangan (penjamin tepat sekali, bentrok bersamaan juga 409 `KANDIDAT_SUDAH_DITERAPKAN`). `KonteksRead` bertambah `ai_usulan_id` dan `ai_kandidat_indeks` (aditif, null untuk konteks manual/seed); `ai_usulan_id` dapat dipakai di `POST /api/v1/redesain/konteks/search`. `KonteksCreate`/`KonteksUpdate` tidak berubah. Tes pengunci himpunan rute `/api/v1/ai/usulan` menyesuaikan rute baru.
- **Fungsi P11: pengusul konteks redesain** (backlog #127): `POST /api/v1/redesain/konteks/usulan-ai` (202 `AiUsulanRingkas`, sasaran `REDESAIN_KONTEKS`, `sasaran_id` `KATALOG`; `tim-kajian`; `Idempotency-Key`; badan `PengajuanP11` = `sertakan_masalah` (bawaan `true`), `jumlah_kandidat` (1-5, bawaan 3), `sumber_dokumen_ids` (maks. 5)). Dokumen tak ada 404, tanpa izin AI 409 `izin_sumber_tidak_ada`; nol konteks aktif 422 `TANPA_KONTEKS`; lebih dari 60 sumber redesain 422 `SUMBER_TERLALU_BANYAK`; fungsi belum terdaftar 409 `fungsi_belum_aktif`. Perakit `rakit_sumber_konteks` (`ai/sumber_konteks.py`) dengan jenis `REDESAIN`: `konteks:` (konteks aktif) dan `masalah:` (masalah berkonteks aktif, tanpa sekolah, keterangan sekolah, maupun kode orang PIC); dokumen dengan jenisnya sendiri. `parameter` = `jumlah_kandidat`, `sertakan_masalah`, `kode_konteks_ada`; dua batas disimpan di `ai_usulan.konteks_server` dan diteruskan penyerap ke aturan isi. Skema `isi`: `konteks_candidates` (minimal satu; `tema`, `ruang_dugaan`, `sumber_draft`, `batas_pemeriksaan`, `gelombang_saran` nilai `Gelombang`, `mirip_kode` string/null, `source_ids`) dan `reviewer_questions`. Aturan isi `aturan_p11`: `RUJUKAN_TAK_DIKENAL`, `KODE_KONTEKS_TAK_DIKENAL`, `KANDIDAT_BERLEBIH`, `TEMA_TERLALU_PANJANG` (usulan `MANUAL`). P11 masuk `KATALOG_FUNGSI`; `AI_FUNGSI_AKTIF` dan `AI_JENIS_SUMBER_DIIZINKAN` bawaan tidak berubah. `make eval-ai FUNGSI=P11` dikenal (3 kasus sintetis minimal). **Evaluasi nyata P11 belum dijalankan dan wajib lulus sebelum diaktifkan.** Tes lama yang mengunci isi `KATALOG_FUNGSI` dan `ATURAN_ISI` menyesuaikan entri P11.
- **Fungsi P07: kartu keputusan dengan `authorization_state` dari server** (backlog #125, revisi `e4a7c19b2d63`): `POST /api/v1/redesain/masalah/{masalah_id}/kartu-keputusan-ai` (202 `AiUsulanRingkas`, sasaran `REDESAIN_MASALAH`; `tim-kajian`; `Idempotency-Key`; badan `PengajuanP07` = `periode` dan opsional `usulan_p06_id`). Syarat `periksa_syarat_p07` = gerbang F4 P06 ditambah minimal satu alternatif (`ALTERNATIF_BELUM_ADA`); gagal 409 `SYARAT_F4_BELUM_TERPENUHI` sebelum run dibuat (kode di `details[].code`). Masalah atau usulan tak ada 404; usulan bukan P06 atau milik masalah lain 422 `USULAN_BUKAN_P06`; usulan P06 belum diterima 409 `USULAN_BELUM_DITERIMA`; fungsi belum terdaftar 409 `fungsi_belum_aktif`. Kolom baru `ai_usulan.konteks_server` (JSONB, null untuk fungsi lain) menyimpan `{"authorization_state": {alternatif[] (alternatif_id, status_telaah, pemutus_kode_orang, keputusan, prasyarat_monitoring), prioritas_final, change_ditandatangani: false, sumber: "server", diambil_pada}}` yang dibaca server, bukan oleh model; ikut di detail `GET /api/v1/ai/usulan/{id}` (`AiUsulanRead.konteks_server`). Sumber: perakit redesain, alternatif, `otorisasi:<masalah_id>` (salinan baca status otorisasi), dan opsional usulan P06. Skema `isi`: `decision_card` (masalah, bukti, alternatif, batas angka, risiko, persyaratan), `limitation` (minimal satu, ditolak skema bila kosong), `required_signoffs` (`jenis` PRIORITY/CHANGE, `status` const `BELUM_DITANDATANGANI`), tanpa kunci `authorization_state`. Aturan isi `aturan_p07`: `RUJUKAN_TAK_DIKENAL`, `STATUS_TERLARANG` (dipakai bersama P06 lewat `memuat_status_terlarang`), `CHANGE_TIDAK_DISEBUT`, `UNKNOWNS_KOSONG` (usulan `MANUAL`). Rute Yayasan tidak berubah. P07 masuk `KATALOG_FUNGSI`; `AI_FUNGSI_AKTIF` dan `AI_JENIS_SUMBER_DIIZINKAN` bawaan tidak berubah. `make eval-ai FUNGSI=P07` dikenal (3 kasus sintetis minimal). **Evaluasi nyata P07 belum dijalankan dan wajib lulus sebelum diaktifkan.** Tes lama yang mengunci isi `KATALOG_FUNGSI`, `ATURAN_ISI`, dan himpunan field detail usulan menyesuaikan entri P07.
- **Fungsi P08: sintesis bukti riset** (backlog #126): `POST /api/v1/riset/protokol/{protokol_id}/sintesis-ai` (202 `AiUsulanRingkas`, sasaran `PROTOKOL_RISET`; `tim-kajian`; `Idempotency-Key`; badan `PengajuanP08` = `periode`). Protokol tak ada 404; fungsi belum terdaftar 409 `fungsi_belum_aktif`; protokol `DRAF` 409 `PROTOKOL_BELUM_TERKUNCI`; nol statistik `TERVERIFIKASI` 409 `STATISTIK_TERVERIFIKASI_KOSONG`; lebih dari 60 sumber 422 `SUMBER_TERLALU_BANYAK`; semuanya sebelum run dibuat. Perakit `rakit_sumber_riset` (`ai/sumber_riset.py`) dengan jenis sumber baru `RISET`: `protokol:` (kode, versi, `isi_hash`, isi), `statistik:` (hanya `TERVERIFIKASI`), `kasus-negatif:`, `versi-metode:` (`redesain_versi_metode`); statistik `DRAF` dan identitas orang tidak dikirim. `parameter` hanya `protokol_kode`, `protokol_versi`, `periode`. Skema `isi`: `manuscript_sections` (`bagian` METODE/HASIL, `teks`, `source_ids`), `evidence_table` (`klaim`, `statistik_ids`, `batasan`), `limitations` (minimal satu, ditolak skema bila kosong), `unsupported_claims`. Aturan isi `aturan_p08`: `RUJUKAN_TAK_DIKENAL` (termasuk `source_ids` kosong), `KLAIM_TANPA_STATISTIK` (termasuk `statistik_ids` kosong), `HASIL_TANPA_STATISTIK`, `KLAIM_TERLARANG` (kata utuh `Q1`; `signifikan`/`non-inferior` di bagian tanpa sumber `statistik:`) (usulan `MANUAL`). P08 masuk `KATALOG_FUNGSI`; `AI_FUNGSI_AKTIF` dan `AI_JENIS_SUMBER_DIIZINKAN` bawaan tidak berubah; README mencatat label `RISET` dan penahanan KTK:192/OD-09 sebagai pertimbangan aktivasi. `make eval-ai FUNGSI=P08` dikenal (3 kasus sintetis minimal). **Evaluasi nyata P08 belum dijalankan dan wajib lulus sebelum diaktifkan.** Tiga tes lama yang mengunci isi `KATALOG_FUNGSI` dan `ATURAN_ISI`, serta himpunan rute `/riset/protokol`, menyesuaikan entri P08.
- **Fungsi P06: draf opsi redesain dengan gerbang F4** (backlog #124): `POST /api/v1/redesain/masalah/{masalah_id}/opsi-ai` (202 `AiUsulanRingkas`, sasaran `REDESAIN_MASALAH`; `tim-kajian`; `Idempotency-Key`; badan `PengajuanP06` = `periode`). Gerbang F4 bersama `periksa_syarat_f4` (`ai/syarat_f4.py`, dipakai ulang P07) dengan **definisi sementara** `VERSI_SYARAT_F4 = "sementara-2026-11"`: penilaian `Diperkuat untuk klaim` (`KLAIM_BELUM_TERVALIDASI`), minimal satu bukti `Diperiksa sesuai klaim` (`AUDIT_BUKTI_BELUM_MINIMAL`), tanpa bukti `Diperselisihkan` (`BUKTI_DIPERSELISIHKAN`); gagal dibalas 409 `SYARAT_F4_BELUM_TERPENUHI` sebelum run dibuat, kode syarat di `details[].code` (`loc: ["alasan"]`). Masalah tak ada 404; fungsi belum terdaftar 409 `fungsi_belum_aktif`. Sumber: `rakit_sumber_redesain` dengan konfirmasi terkirim ditambah `alternatif:<id>` (`rakit_sumber_alternatif`; opsi, penerima, komitmen, jadwal puncak, keterampilan/akses, tambahan bersih, gap, risiko). `parameter` memuat `versi_syarat_f4` dan `source_verified_quantities` (selalu kosong). Skema `isi`: `options` (`jenis` STATUS_QUO/SIMPLIFY/AUTOMATE/TRANSFER, `opsi_aplikasi` salah satu `OpsiAlternatif` atau null, `fakta_sumber`, `asumsi`), `scenario_assumptions`, `unknown_parameters` (minimal satu, ditolak skema bila kosong), `risks`/`checks` (`opsi_ke`, satu-satunya field numerik). Aturan isi `aturan_p06`: `RUJUKAN_TAK_DIKENAL`, `STATUS_TERLARANG` (kata utuh VERIFIED/READY/APPROVE), `ANGKA_FTE` (usulan `MANUAL`). P06 masuk `KATALOG_FUNGSI`; `AI_FUNGSI_AKTIF` dan `AI_JENIS_SUMBER_DIIZINKAN` bawaan tidak berubah. `make eval-ai FUNGSI=P06` dikenal (3 kasus sintetis minimal). **Evaluasi nyata P06 belum dijalankan dan wajib lulus sebelum diaktifkan.** Tiga tes lama yang mengunci isi `KATALOG_FUNGSI` dan `ATURAN_ISI` menyesuaikan entri P06.
- **Fungsi P05: hipotesis proses dengan syarat sumber terhubung** (backlog #121): `POST /api/v1/redesain/masalah/{masalah_id}/hipotesis-proses-ai` (202 `AiUsulanRingkas`, sasaran `REDESAIN_MASALAH`; `tim-kajian`; `Idempotency-Key`; badan `PengajuanP05` = `periode`). Masalah tak ada 404; belum ada proses dengan minimal satu langkah 409 `SUMBER_PROSES_BELUM_TERHUBUNG` (MX:10); lebih dari 60 sumber 422 `SUMBER_TERLALU_BANYAK`; fungsi belum terdaftar 409 `fungsi_belum_aktif`. Perakit bersama `rakit_sumber_redesain` (`ai/sumber_redesain.py`, disiapkan untuk P06/P07) dengan jenis sumber baru `REDESAIN`: `masalah:` (memuat `task_links` uraian tugas tertaut), `proses:`, `langkah:`, `bukti:`, `koreksi:`, `konfirmasi:`; konfirmasi hanya yang `dikirim_pada` terisi, tanpa `cerita_sebelum` (KAI:15). Skema `isi`: `process_draft.langkah`, `issue_hypotheses` (`status` const `HIPOTESIS`), `disconfirming_checks`, `evidence_gaps`. Aturan isi `aturan_p05`: `RUJUKAN_TAK_DIKENAL` (termasuk `source_ids` kosong), `HIPOTESIS_TANPA_PENYANGKAL` (usulan `MANUAL`). P05 masuk `KATALOG_FUNGSI`; `AI_FUNGSI_AKTIF` dan `AI_JENIS_SUMBER_DIIZINKAN` bawaan tidak berubah. `make eval-ai FUNGSI=P05` dikenal (3 kasus sintetis minimal). **Evaluasi nyata P05 belum dijalankan dan wajib lulus sebelum diaktifkan.**
- **Fungsi P03 versi terbatas: tag peran berdasarkan mandat formal** (backlog #120): `POST /api/v1/task-inventory/jabatan/{jabatan_id}/tag-peran-ai` (202 `AiUsulanRingkas`, sasaran `JABATAN`; `tim-kajian`; `Idempotency-Key`; badan `PengajuanP03` = `usulan_p02_id` (UUID) dan `periode`). Sumber hanya usulan P02 yang sudah diterima reviewer (`USULAN_AI`) dan baris `ti_uraian_tugas_jabatan` dari semua jabatan untuk uraian yang dirujuk `source_ids` usulan itu (`KATALOG_TI`, `uraian:<uraian_id>@<jabatan_id>`, teks hanya kode/nama jabatan dan field tugas). Tidak ada sumber penugasan aktual. Jabatan atau usulan tak ada 404; usulan bukan P02 atau milik jabatan lain 422 `USULAN_BUKAN_P02`; usulan belum diterima 409 `USULAN_BELUM_DITERIMA`; lebih dari 80 sumber 422 `SUMBER_TERLALU_BANYAK`; fungsi belum terdaftar 409 `fungsi_belum_aktif`. Skema `isi`: `tag_candidates` (`kandidat_ke`, `jabatan_kode`, `dasar` const `MANDAT_FORMAL`, `status_aktual` const `BELUM_DIKETAHUI`, `source_ids`) dan `owner_ambiguities`. Aturan isi `aturan_p03`: `RUJUKAN_TAK_DIKENAL`, `TANPA_DASAR_MANDAT`, `UNKNOWNS_KOSONG` (usulan `MANUAL`). P03 masuk `KATALOG_FUNGSI`; `AI_FUNGSI_AKTIF` dan `AI_JENIS_SUMBER_DIIZINKAN` bawaan tidak berubah. `make eval-ai FUNGSI=P03` dikenal (3 kasus sintetis minimal). README mencatat batas versi terbatas dan syarat membukanya. **Evaluasi nyata P03 belum dijalankan dan wajib lulus sebelum diaktifkan.** Tiga tes lama yang mengunci isi `KATALOG_FUNGSI` dan `ATURAN_ISI` menyesuaikan entri P03.
- **Fungsi P02: normalisasi tugas katalog menjadi kandidat tugas baku** (backlog #118): `POST /api/v1/task-inventory/jabatan/{jabatan_id}/normalisasi-ai` (202 `AiUsulanRingkas`; `tim-kajian`, `admin` tidak otomatis lolos; `Idempotency-Key`; badan `PengajuanP02` = `unit` (kode, opsional), `periode` (`POLA_PERIODE_AI`), `sumber_dokumen_ids` (maks. 5)). Tiap baris `ti_uraian_tugas_jabatan` milik jabatan (dipersempit `unit` bila diisi) dikirim sebagai sumber berjenis baru `KATALOG_TI` dengan `source_id` `uraian:<ti_uraian_tugas.id>`; teksnya hanya field tugas dan nilai standar. Dokumen `narasi_sumber` ikut dengan jenisnya sendiri (tak ada 404, tanpa izin AI 409 `izin_sumber_tidak_ada`). Jabatan tak ada 404; 0 baris katalog 422 `TANPA_URAIAN`; lebih dari 80 baris 422 `URAIAN_TERLALU_BANYAK` (persempit dengan `unit`); fungsi belum terdaftar 409 `fungsi_belum_aktif`. `parameter` hanya `jabatan_kode`, `unit`, `periode`. Skema `isi`: `task_candidates` (tindakan, objek, tujuan, cara, output, `tingkat` `DUTY`/`TASK`/`ACTIVITY`, `source_ids`), `duplicate_suspicions`, `split_merge_rationale` (`PECAH`/`GABUNG`), `reviewer_questions`; tanpa field persetujuan, skor, atau keputusan. Aturan isi `aturan_p02` di `ATURAN_ISI`: `source_ids` yang tak ada di `amplop.source_refs` memberi usulan `MANUAL` `RUJUKAN_TAK_DIKENAL`; jumlah minimum `source_ids` (kandidat dan pecah/gabung >= 1, dugaan duplikasi >= 2) ditagih server dengan kode `RUJUKAN_KURANG` karena skema structured output tidak boleh memakai `minItems`. Hasil hanya usulan bersasaran `JABATAN`; katalog TI tidak ditulis dan promosi kandidat tetap jalur manusia. P02 masuk `KATALOG_FUNGSI` tetapi `AI_FUNGSI_AKTIF` bawaan tetap `[]` dan `AI_JENIS_SUMBER_DIIZINKAN` bawaan tetap `["SINTETIS"]` (README mencatat `KATALOG_TI` dan `USULAN_AI` sebagai keputusan aktivasi). `make eval-ai FUNGSI=P02 PENYEDIA=<jalur>` kini dikenal (3 kasus sintetis minimal di `evals/p02/kasus.json`). **Evaluasi nyata P02 belum dijalankan dan wajib lulus sebelum diaktifkan.** Dua tes lama menyesuaikan isi katalog dan `ATURAN_ISI` yang kini memuat P02.
- **Kasus negatif riset, append-only** (backlog #123, revisi `ca3b9bb3b458`): tabel baru `riset_kasus_negatif` (`protokol_id` FK `riset_protokol` `ON DELETE RESTRICT` berindeks, `ringkasan`, `alasan_negatif`, `sumber_ref` opsional, `dibuat_oleh`, `created_at`) dan dua rute khusus `tim-kajian` (`admin` tidak otomatis lolos): `POST /api/v1/riset/protokol/{protokol_id}/kasus-negatif` (201, `Idempotency-Key`, pencatat dari token; protokol tak ada 404, protokol `DRAF` 409 `PROTOKOL_BELUM_TERKUNCI`) dan `GET /api/v1/riset/protokol/{protokol_id}/kasus-negatif` (halaman urut waktu pencatatan, terlama dulu; 404 bila protokol tak ada). `ringkasan` dan `alasan_negatif` 1-5.000 karakter (tak boleh hanya spasi), `sumber_ref` maks. 500. `dibuat_oleh` di body diabaikan (field asing lain tetap 422). Tidak ada sunting maupun hapus. Isi ditujukan untuk deskripsi kasus tersamar; tidak ada penyaringan PII baru (gerbang PII gateway tetap berlaku saat dikirim ke model). Fungsi P08 tetap item terpisah.
- **Statistik riset dengan verifikasi independen** (backlog #122, revisi `aa0aebd31d4a`): tabel baru `riset_statistik` (`protokol_id` FK `riset_protokol` `ON DELETE RESTRICT` berindeks, `nama_analisis`, `keluaran` (keluaran kode analisis apa adanya), `kode_sumber_ref` (skrip + commit penghasil), `status` `DRAF`/`TERVERIFIKASI` dijaga CHECK, `dibuat_oleh`, `diverifikasi_oleh`, `diverifikasi_pada`) dan tiga rute khusus `tim-kajian` (`admin` tidak otomatis lolos): `POST /api/v1/riset/protokol/{protokol_id}/statistik` (201 `DRAF`, `Idempotency-Key`, pengunggah dari token; protokol tak ada 404, protokol `DRAF` 409 `PROTOKOL_BELUM_TERKUNCI`), `GET /api/v1/riset/protokol/{protokol_id}/statistik` (halaman, filter `status`, 404 bila protokol tak ada), dan `POST /api/v1/riset/statistik/{statistik_id}/verifikasi` (200 `TERVERIFIKASI` dengan pemverifikasi dari token; 404; 409 `STATISTIK_SUDAH_TERVERIFIKASI`; 409 `PEMVERIFIKASI_TIDAK_INDEPENDEN` bila pemverifikasi = pengunggah). `keluaran` 1-200.000 karakter, `kode_sumber_ref` wajib tak kosong (maks. 500). Tidak ada sunting, hapus, maupun pembatalan verifikasi: koreksi dibuat sebagai statistik baru. Fungsi P08 dan kasus negatif tetap item terpisah.
- **Protokol riset berversi yang dapat dikunci** (backlog #119, revisi `26b72008801d`): tabel baru `riset_protokol` (`kode`, `versi`, `judul`, `isi`, `status` `DRAF`/`TERKUNCI` dijaga CHECK, `isi_hash`, `dibuat_oleh`, `dikunci_oleh`, `dikunci_pada`; UNIQUE (`kode`, `versi`)) dan empat rute khusus `tim-kajian` (`admin` tidak otomatis lolos) di `/api/v1/riset/protokol`: `POST ''` (201, status `DRAF`, `versi` = versi terbesar `kode` itu + 1, `Idempotency-Key`), `GET ''` (ringkas tanpa `isi`, filter `kode`/`status`), `GET /{id}` (404 bila tak ada), `POST /{id}/kunci` (set `TERKUNCI`, `isi_hash` SHA-256 heksadesimal `isi`, aktor dari token; kunci ulang 409 `PROTOKOL_TERKUNCI`). Tidak ada PATCH/PUT/DELETE maupun buka-kunci: perbaikan draf dan revisi dibuat sebagai protokol baru berkode sama. `kode` mengikuti pola `^[A-Za-z0-9_.:-]+$` (maks. 40), `isi` 1-100.000 karakter. Aktivasi P08 tetap terpisah.
- **Rangkaian usulan AI** (backlog #118): `AiUsulanService.sumber_dari_usulan(usulan_id)` membungkus usulan yang sudah diterima reviewer sebagai sumber berjenis `USULAN_AI` (`usulan:<id>`): putusan terakhir `APPROVE` memakai JSON kanonik `isi`, `REVISE` memakai `teks_koreksi`; tanpa putusan, `REJECT`, atau `APPROVE` atas usulan tanpa `isi` menghasilkan 409 `USULAN_BELUM_DITERIMA`. Belum ada rute yang memakainya (disiapkan untuk P03 dan P07); gerbang jenis dan PII gateway tidak dilonggarkan.

### Diubah

- **`SasaranUsulan` bertambah `JABATAN`, `REDESAIN_MASALAH`, `PROTOKOL_RISET` dan `ai_usulan.sasaran_id` melebar ke 40 karakter** (backlog #118, revisi `12a4ee50e4f3`): CHECK `ck_ai_usulan_sasaran_jenis` diperbarui sekali untuk seluruh batch fungsi berikutnya; `sasaran_id` `String(36)` menjadi `String(40)` agar id `jabatan` muat utuh. `downgrade()` membalik keduanya dan gagal bila masih ada baris bernilai sasaran baru atau `sasaran_id` lebih dari 36 karakter. Skema `AiUsulanRingkas.sasaran_jenis` di OpenAPI bertambah tiga nilai enum (aditif).

## [0.49.0] - 2026-11-06

### Diperbaiki

- **Span fakta P01 kini ditagih server** (backlog #116): usulan P01 berstatus `USULAN_DIBUAT` hanya bila setiap `factual_extracts[].span` (setelah spasi dinormalkan, peka huruf besar-kecil) merupakan potongan dari kutipan pada `cited_spans` ber-`source_id` sama; selain itu usulan `MANUAL` tanpa `isi`, `amplop`, dan `output_hash` dengan `kode_serap == ["SPAN_FAKTA_TIDAK_DITEMUKAN"]` (satu kali per usulan; mencakup span kosong, `source_id` asing, dan span tak terbukti), sedangkan `ai_run.status_qa` tetap `LOLOS`. Pembuktian lewat `cited_spans` karena `ai_run.masukan` dikosongkan saat run ditutup. `EVIDENCE_GAP` dan P04 tidak berubah. Perubahan internal: signature `ATURAN_ISI` menjadi `(isi, amplop)` untuk semua fungsi dan `_norm` di `ai/keluaran.py` menjadi `normalkan_kutipan`. Tanpa migrasi, tanpa perubahan kontrak HTTP. **P01 tidak boleh masuk `AI_FUNGSI_AKTIF` sebelum item ini selesai** dan evaluasi nyata P01 tetap wajib lulus.

### Diubah

- **`periode` `2026/27` diterima apa adanya oleh fungsi AI** (backlog #117): satu pola bersama `POLA_PERIODE_AI = ^[A-Za-z0-9_.:/-]+$` (`ai/masukan.py`) dipakai `periode` pada P10, P01, P04, dan badan `POST /api/v1/narasi/sumber/{id}/ekstraksi-ai`; hanya garis miring yang ditambahkan, spasi tetap ditolak, dan `instrument_id`, `field_key`, `peran_ref` tidak berubah. P04 tidak lagi mengubah karakter `periode` kasus (`kode_periode_p04` dihapus): `2026/27` dan `2026-27` kini menjadi dua nilai berbeda pada `parameter` run. **Perubahan perilaku**: `POST /api/v1/narasi/kasus/{id}/tanya-bukti-ai` untuk kasus berperiode di luar pola (mis. `2026/27 ganjil`) kini 422 `validation_error` dengan pesan `Periode kasus tidak sesuai pola parameter AI.` tanpa baris `ai_run` maupun `ai_usulan` (sebelumnya 202 dengan karakter diganti `-`); pemeriksaan berada di dalam aksi idempoten setelah flag, kasus, dan sumber, sehingga flag mati tetap 409. Kasus berperiode `2026/27` yang sebelumnya ditolak 422 pada permintaan draf P10 kini lolos pola. Deskripsi 422 OpenAPI endpoint P04 diperbarui. Tanpa migrasi.
- **`actor_key` keluar dari `putusan_terakhir` pada daftar dan pencarian usulan AI** (backlog #115): `GET /api/v1/ai/usulan` dan `POST .../search` kini memuat `putusan_terakhir` berisi persis `id`, `putusan`, `tingkat_koreksi`, `created_at` (skema baru `AiUsulanPutusanRingkas`); subjek reviewer tidak lagi keluar di baris daftar dan kueri daftar tidak lagi memilih kolom `actor_key` (jumlah kueri tetap). **Perubahan kontrak yang memutus pemakai daftar dan pencarian**: `components.schemas.AiUsulanRingkas.putusan_terakhir` merujuk `AiUsulanPutusanRingkas`. Detail `GET .../{id}` (`putusan_terakhir` dan tiap `putusan[]`) dan respons `POST .../putusan` (termasuk replay `Idempotency-Key`) tetap memuat `actor_key`. Domain atau urutan pada `actor_key` tetap 422 dan `?actor_key=` pada `GET` tetap diabaikan (200, hasil sama). Belum ada tag yang memuat rute ini, tanpa masa transisi; tanpa migrasi.
- **Daftar dan pencarian usulan AI dibatasi ke sembilan field** (backlog #114): `GET /api/v1/ai/usulan` dan `POST .../search` tidak lagi memuat `ai_run_id`, `sumber_ids`, dan `diminta_oleh` (identitas pemohon); item berisi sembilan field #102 ditambah `putusan_terakhir` (#103). **Perubahan kontrak yang memutus pemakai daftar dan pencarian**: `components.schemas.AiUsulanRingkas` kehilangan tiga properti wajib. Detail `GET .../{id}` tetap memuat ketiganya (wajib terisi; `AiUsulanRead` kini mendeklarasikannya sendiri), jadi himpunan kunci dan nilainya tidak berubah. `AiUsulanService.ajukan` ikut mengembalikan proyeksi yang menyempit. Whitelist pencarian dan filter daftar tidak berubah (domain atau urutan pada ketiga field tetap 422). Belum ada tag yang memuat rute ini, tanpa masa transisi; tanpa migrasi.
- **Tujuan dan header klien Anthropic dikunci dari env SDK** (backlog #113): `AnthropicKlienModel` selalu memakai `base_url=https://api.anthropic.com` dan mengosongkan header dari `ANTHROPIC_CUSTOM_HEADERS` setelah konstruksi, sehingga `ANTHROPIC_BASE_URL`/`ANTHROPIC_CUSTOM_HEADERS` tidak lagi dapat mengalihkan kunci dan prompt atau menimpa header kredensial. Bila klien SDK tidak punya `_custom_headers` (SDK berubah), `KesalahanModelPermanen` dilempar tanpa permintaan. `pyproject.toml` memakai `anthropic==2.5.0` (sebelumnya `>=2.4,<3`); menaikkan versi wajib lewat uji. Tanpa migrasi, tanpa env baru.

### Ditambahkan

- **Fungsi P04: usulan satu pertanyaan bukti netral, tanpa pengiriman** (backlog #106): `POST /api/v1/narasi/kasus/{id}/tanya-bukti-ai` (202 `AiUsulanRingkas`; `tim-kajian`, `admin` tidak otomatis lolos; `Idempotency-Key`; badan `klaim` 5-2.000 karakter, `keputusan_terkait` 5-500 karakter, `sumber_ids` minimal satu). Spasi tepi `klaim` dan `keputusan_terkait` dipangkas sebelum panjang diperiksa. Keduanya teks bebas, jadi dikirim sebagai sumber `klaim:<uuid>` dan `keputusan:<uuid>` (UUID5 atas isi teks, jenis = jenis sumber pertama) agar ikut gerbang PII, bukan sebagai `parameter`; email atau data pribadi pada salah satunya menghasilkan run `DIBLOKIR` dan usulan `MANUAL` tanpa panggilan model. Penanda itu tercatat di `sumber_ids` detail usulan dan bukan baris `narasi_sumber`. `parameter` hanya `narasi_id` dan `periode`; `periode` kasus di luar pola `^[A-Za-z0-9_.:-]+$` (mis. `2026/27`) diubah karakternya menjadi `-` agar kasus sah tidak ditolak. Kasus tak ada 404, sumber tak dikenal 422, sumber `izin_ai=false` 409 `izin_sumber_tidak_ada`; seluruh pemeriksaan di dalam aksi idempoten. Aturan isi `aturan_p04` terdaftar di `ATURAN_ISI`: `material=true` tanpa pertanyaan atau `material=false` dengan pertanyaan memberi usulan `MANUAL` `ATURAN_P04_DILANGGAR`, lebih dari satu tanda tanya `LEBIH_DARI_SATU_PERTANYAAN`; pertanyaan kosong atau hanya spasi dianggap tidak ada. Kenetralan tidak diperiksa mesin (tugas reviewer). Hasil hanya usulan di `ai_usulan` bersasaran `NARASI_KASUS`: tidak menulis `narasi_*`, tidak memanggil notifikasi, tidak membuat permintaan bukti. P04 masuk `KATALOG_FUNGSI` tetapi tidak terdaftar sampai operator menyebutnya di `AI_FUNGSI_AKTIF`; `FEATURE_AI_NARRATIVE_DRAFT` tetap `false`. `make eval-ai FUNGSI=P04 PENYEDIA=<jalur>` kini dikenal (8 kasus sintetis di `evals/p04/kasus.json`; penilai khas P04, perilaku penilai P01, P09, dan P10 tidak berubah). **Evaluasi nyata P04 belum dijalankan dan wajib lulus sebelum diaktifkan.** Tanpa migrasi; dua tes lama menyesuaikan isi katalog dan `ATURAN_ISI` yang kini memuat P04.
- **Fungsi P01: ekstraksi fakta AI dari dokumen sumber** (backlog #105): `POST /api/v1/narasi/sumber/{id}/ekstraksi-ai` (202 `AiUsulanRingkas`; `tim-kajian`, `admin` tidak otomatis lolos; `Idempotency-Key`; badan hanya `peran_ref` dan `periode` berpola `^[A-Za-z0-9_.:-]+$`, maks. 100 karakter, tanpa teks bebas). Satu rute satu sumber; sumber tak ada 404, `izin_ai=false` 409 `izin_sumber_tidak_ada`, dan seluruh pemeriksaan berada di dalam aksi idempoten (ulangan dengan key sama membalas respons tersimpan). Gerbang jenis dan PII berlaku persis seperti fungsi lain: `DOKUMEN_RESMI` di luar `AI_JENIS_SUMBER_DIIZINKAN` memberi run `DIBLOKIR` `JENIS_DITOLAK`, email pada teks memberi `PII_DITEMUKAN`, keduanya usulan `MANUAL` tanpa panggilan model. Usulan bersasaran `NARASI_SUMBER`; `narasi_sumber`, `narasi_kasus`, `narasi_versi`, dan `narasi_event` tidak ditulis. Skema `isi`: `factual_extracts` (`sifat` `NORMATIF`/`DESKRIPTIF_DOKUMEN`), `source_quality` (`CUKUP`/`TERBATAS`/`TIDAK_JELAS`), `uncertainties`, `limitations`; tanpa field persetujuan, skor, atau keputusan. Instruksi melarang menyimpulkan praktik terlaksana dari dokumen normatif dan mengarang angka. P01 masuk `KATALOG_FUNGSI` tetapi tidak terdaftar sampai operator menyebutnya di `AI_FUNGSI_AKTIF`; `FEATURE_AI_NARRATIVE_DRAFT` tetap `false`. `make eval-ai FUNGSI=P01 PENYEDIA=<jalur>` kini dikenal (10 kasus sintetis di `evals/p01/kasus.json`; penilai khas P01, perilaku penilai P09 dan P10 tidak berubah). **Evaluasi nyata P01 belum dijalankan dan wajib lulus sebelum diaktifkan.** Tanpa migrasi; tes lama `test_daftar_p10_idempoten_dan_dikosongkan` menyesuaikan isi katalog.
- **Fungsi P09: kritik AI atas versi narasi sebagai pembantu reviewer** (backlog #104): `POST /api/v1/narasi/kasus/{id}/kritik-ai` (202 `AiUsulanRingkas`; `tim-kajian`, `admin` tidak otomatis lolos; `Idempotency-Key`; badan `narasi_versi_id`). Pemeriksaan 404 dan 409 (`versi_basi`, `narasi_tanpa_teks`, `kritik_tanpa_sumber`, `izin_sumber_tidak_ada`) berada di dalam aksi idempoten, jadi ulangan dengan key sama membalas respons tersimpan. Draf dikirim sebagai sumber `versi:<id>` (jenis = jenis sumber pertama menurut urutan tautan) sehingga ikut gerbang PII; email atau data pribadi pada draf menghasilkan run `DIBLOKIR` dan usulan `MANUAL` tanpa panggilan model. `sumber_ids` pada detail usulan memuat `versi:<id>` sebagai entri terakhir (bukan baris `narasi_sumber`). Hasil hanya usulan di `ai_usulan`: tidak menulis `narasi_versi`, `narasi_versi_sumber`, `narasi_event`, maupun `narasi_ai_permintaan`, tidak mengubah status kasus, `jumlah_sumber`, `jumlah_kontradiksi`, atau antrean. Skema `isi` tanpa field persetujuan, skor, atau keputusan (`peran` const `REVIEWER_OTOMATIS_PEMBANTU`). P09 masuk `KATALOG_FUNGSI` tetapi tidak terdaftar sampai operator menyebutnya di `AI_FUNGSI_AKTIF`; `FEATURE_AI_NARRATIVE_DRAFT` tetap `false`. `make eval-ai FUNGSI=P09` kini dikenal (12 kasus sintetis di `evals/p09/kasus.json`; penilai menilai kategori temuan, draf bersih, dan span, tidak mengubah hasil P10). **Evaluasi nyata P09 belum dijalankan dan wajib lulus sebelum diaktifkan.** Tanpa migrasi; tes lama `test_daftar_p10_idempoten_dan_dikosongkan` menyesuaikan isi katalog.
- **Putusan reviewer append-only atas usulan AI** (backlog #103): tabel `ai_usulan_putusan` (revisi `cc4cbfe34e90`) dan `POST /api/v1/ai/usulan/{id}/putusan` (201; `tim-kajian`, `admin` tidak otomatis lolos; `Idempotency-Key`; aktor dari token, aktor pada body diabaikan). Putusan `APPROVE`/`REVISE`/`REJECT`; `REVISE` wajib `teks_koreksi` dan `tingkat_koreksi` (`MINOR`/`MAJOR`/`CRITICAL`), `REJECT` wajib `catatan` min. 5 karakter dan `tingkat_koreksi`, `APPROVE` tidak boleh membawa `tingkat_koreksi`/`teks_koreksi`. Usulan belum diserap atau `MANUAL` -> 409 `usulan_belum_bisa_diputus`. `AiUsulanRingkas` bertambah `putusan_terakhir` (tanpa `catatan`/`teks_koreksi`, satu kueri tambahan per halaman) dan `AiUsulanRead` bertambah `putusan[]` urut naik. Tanpa PATCH/DELETE; hanya catatan audit: tidak menulis `narasi_*`, tidak mengirim apa pun. `FEATURE_AI_NARRATIVE_DRAFT` tetap `false`.
- **Rute baca usulan AI untuk Tim Kajian** (backlog #102): `GET /api/v1/ai/usulan` (filter `fungsi`, `sasaran_jenis`, `sasaran_id`, `hasil_serap`), `POST .../search` (whitelist `fungsi`, `sasaran_jenis`, `sasaran_id`, `hasil_serap`, `created_at`; field lain 422) dan `GET .../{id}` (memuat `isi`, `amplop`, `output_hash`). Semua rute `require_tim_kajian` (`admin` tidak otomatis lolos); daftar dan pencarian tanpa `isi`/`amplop`, kolom itu tidak dibaca dari basis data pada kedua rute tersebut. Read-only (tanpa PATCH/DELETE); `masukan` dan `keluaran` run tetap tertutup. Tanpa migrasi; `FEATURE_AI_NARRATIVE_DRAFT` bawaan tetap `false`.
- **Harness evaluasi P10 dua jalur di luar `make test`** (backlog #100): `make eval-ai FUNGSI=P10 PENYEDIA=<API_ANTHROPIC|LANGGANAN_CLAUDE> [CLAUDE_VOLUME=<volume>]` membangun image evaluasi (`Dockerfile.eval` di atas target `runtime`) dan menjalankan `python -m evals.jalankan` dengan 17 kasus sintetis (`evals/p10/kasus.json`: 4 tanpa model, 13 dengan model) dan penilai deterministik. Vonis dibaca dari baris akhir `#EVAL` (`penyedia`, `model`, `kode`, `exit`) karena `make` mengubah kegagalan resep menjadi exit 2; exit 0-7 dijelaskan di README. Kunci API hanya lewat `docker run -e ANTHROPIC_API_KEY` tanpa nilai; jalur langganan memakai volume Docker bernama dan tidak meneruskan env kunci. `ai/masukan.py` (`peta_sumber`, `susun_masukan_json`) diekstrak dari `ai/worker.py` tanpa mengubah perilaku agar harness dan worker mengirim masukan yang sama. `evals/` tidak masuk image produksi dan CI tidak memanggilnya; tanpa basis data, tanpa migrasi, `FEATURE_AI_NARRATIVE_DRAFT` tetap `false`. **Alat ukur saja: evaluasi nyata belum dijalankan dan harness ini bukan bukti perilaku model.**
- **Driver `LANGGANAN_CLAUDE` berbasis CLI dan binary di image** (backlog #112): `ClaudeCliKlienModel` (`ai/klien.py`) memanggil `claude -p` (keluaran JSON + `--json-schema`, `--tools ""`, tanpa sesi, masukan lewat stdin, cwd kosong, env hanya `PATH`/`HOME`/`CLAUDE_CONFIG_DIR`/`DISABLE_UPDATES`). Timeout mematikan seluruh grup proses. Kode gagal-tertutup tanpa percobaan ulang: `PENYEDIA_TIDAK_TERSEDIA` (binary tidak ada) dan `LANGGANAN_BELUM_MASUK`; stdout, stderr, dan prompt tidak dicatat. Kunci API di basis data tidak dibaca pada mode ini. `Dockerfile` target `runtime` memasang `claude-code` terpin (`CLAUDE_CODE_VERSION=2.1.311-1`) dari repo apt bertanda tangan dengan pemeriksaan sidik jari kunci, dan menyetel `CLAUDE_CONFIG_DIR=/var/lib/claude-config`; **image membesar sekitar 280 MiB**. `make test-arm64` kini memeriksa `claude --version`. README memuat catatan risiko; tanpa migrasi, tanpa env deployment baru.
- **API admin pengaturan penyedia AI** (backlog #110): `GET /api/v1/system/ai/penyedia` dan `POST .../mode`, `.../model`, `.../kredensial`, `.../kredensial/hapus` (hanya grup `admin`, `Idempotency-Key` pada keempat POST, aktor dari token). Kunci API hanya dapat ditulis (min. 20 karakter, `SecretStr`) dan respons hanya memuat empat karakter akhir. Kode galat `422 MODEL_DITOLAK` dan `503 KUNCI_INDUK_TIDAK_ADA` (sebelumnya huruf kecil pada kelas #109, belum pernah terlihat di HTTP). `ai/langganan_cli.py` membaca status CLI langganan dari exit code dengan env daftar-putih; keluaran `claude auth status` dibuang. `inference_geo` dan `refusal_fallback` tampil baca-saja dari env. Memilih penyedia tidak menyalakan AI dan belum dipakai worker (#111); tanpa migrasi, tanpa tool MCP, tanpa env baru.
- **Gateway dan worker AI memakai pengaturan penyedia** (backlog #111): `buat_klien_model` (`ai/penyedia.py`) membaca mode, model, effort, dan kunci API dari basis data tiap pengajuan/job tanpa cache, sehingga perubahan admin berlaku tanpa restart. `AnthropicKlienModel` menerima `kunci_api`, `model`, dan `effort` eksplisit dan tidak lagi membaca `ANTHROPIC_API_KEY`; kunci kosong menghasilkan `KunciModelTidakAda` sebelum klien SDK dibuat. Mode `MATI` membuat `AiGateway.ajukan` menolak (`FiturNonaktifError`) dan job yang sudah antre selesai manual `PENYEDIA_MATI`; `LANGGANAN_CLAUDE` menghasilkan `PENYEDIA_TIDAK_TERSEDIA` sampai driver #112. Kolom baru `ai_run.penyedia` (revisi `0d00a22898a9`) tampil di `AiRunRead`. **Env `AI_MODEL`, `AI_EFFORT`, dan `ANTHROPIC_API_KEY` diabaikan** (field `ai_model`/`ai_effort` dihapus dari `Settings`).
- **Pengaturan penyedia model AI dengan kredensial terenkripsi** (backlog #109): tabel `ai_penyedia_pengaturan` (satu baris) dan `ai_penyedia_event` (append-only), revisi `dc1ef8ebecf9`; `SqlAiPenyediaService` (`status`, `ubah_mode`, `ubah_model`, `pasang_kredensial`, `hapus_kredensial`, `baca_kunci_api`), mode `MATI`/`API_ANTHROPIC`/`LANGGANAN_CLAUDE`, model bawaan `claude-opus-5-5` dan effort `high` (nama `claude-fable*`/`claude-mythos*` ditolak). Kunci API disimpan terenkripsi Fernet; env baru satu-satunya `AI_KREDENSIAL_KUNCI_INDUK` (kosong/salah: pasang kunci ditolak, status tetap terbaca). Dependensi `cryptography` dideklarasikan eksplisit. Memilih penyedia tidak menyalakan AI; belum ada rute HTTP dan belum ada pemanggil `baca_kunci_api`.
- **Tabel `ai_usulan`, pengaju umum, dan penyerapnya** (backlog #101): tabel `ai_usulan` (revisi `e0ba900a9ea4`) menampung hasil fungsi AI non-narasi atas satu sasaran, `AiUsulanService.ajukan` (409 `feature_disabled`, `pii_mode_belum_didukung`, `usulan_berjalan`, `fungsi_belum_aktif`; tanpa baris bila ditolak) dan `serap_usulan_tertunda` yang dipanggil dari loop `narasi.penyerap` yang sama (tanpa entrypoint baru). `LOLOS` menjadi `USULAN_DIBUAT`, `EVIDENCE_GAP` tetap `EVIDENCE_GAP`, sisanya `MANUAL`; semua hasil akhir mengisi `diserap_at`. Registri `ATURAN_ISI` bawaan kosong. Penyerap ini hanya menulis `ai_usulan` (tidak pernah tabel `narasi_*`). Tanpa rute HTTP; `FUNGSI_TERDAFTAR` dan `FEATURE_AI_NARRATIVE_DRAFT` bawaan tidak berubah.
- **Penyerap hasil run AI ke versi narasi** (backlog #99): `python -m anjab_abk_backend.narasi.penyerap` (proses terpisah dari worker; flag `FEATURE_AI_NARRATIVE_DRAFT` mati -> keluar kode 0, selain itu polling tiap `AI_WORKER_POLL_DETIK`). `serap_run` memindahkan run final ke `narasi_versi` lewat `NarasiService.tambah_versi` (aktor `system:ai-worker`, tanpa `narasi_event`): `LOLOS` menjadi versi `AI_DRAFT`, `EVIDENCE_GAP` menjadi versi `NEED_FACT` (teks null), sisanya tanpa versi dengan `hasil_serap=MANUAL` dan `kode_serap`. Semua hasil akhir mengisi `diserap_at` sehingga permintaan tidak menahan kasus; hanya run `MENUNGGU` yang dibiarkan. Metode internal `AiRunService.keluaran_internal` (tanpa rute; `AiRunRead` tetap tanpa `keluaran`). Tanpa migrasi, tanpa rute baru.
- **Rute pengaju draf AI atas kasus narasi** (backlog #98): `POST /api/v1/narasi/kasus/{id}/draf-ai` (202, `tim-kajian`, fungsi P10) dan `GET .../permintaan-ai`; tabel `narasi_ai_permintaan` (revisi `97fef4e3d32c`) menautkan kasus, job, dan `ai_run`. Flag mati bawaan: 409 `feature_disabled` tanpa baris baru. Uji OpenAPI #90 "tanpa rute pengaju" diganti.
- **Antrean reviewer dan rute tinjauan Tim** (backlog #95): `GET /api/v1/narasi/antrean` (kasus `AI_DRAFT`/`TEAM_REVIEW`/`NEED_FACT`, urut `updated_at` naik, tanpa teks; filter `status`, `instrument_id`, `periode`), `GET /api/v1/narasi/antrean/{narasi_id}` (draf berdampingan dengan teks sumber, `contradictions`, `unknowns`, `missing_facts`, `paparan` tetap `TIDAK_BERLAKU`; kasus di luar antrean 409 `narasi_tidak_dalam_antrean`) dan `POST /api/v1/narasi/kasus/{id}/tinjauan` (aksi `TERIMA`/`KOREKSI`/`TOLAK`/`BUTUH_SUMBER` atas `narasi_versi_id` yang dilihat; `Idempotency-Key`). Hanya grup `tim-kajian` (admin tidak otomatis lolos); `actor_role` tetap `tim-kajian`, aktor dari token. `catatan` min. 5 karakter pada `TOLAK`/`BUTUH_SUMBER`; `KOREKSI` membuat versi `REVIEWER_EDIT` dan event dalam satu transaksi; versi basi 409 `versi_basi`; `TERIMA` atas versi tanpa teks 409 `narasi_tanpa_teks`. Hasil `TERIMA` berhenti di `TEAM_VERIFIED`. Tanpa aksi massal, tanpa migrasi; `FEATURE_AI_NARRATIVE_DRAFT` tidak berubah.
- **Rute kasus narasi jalur manual** (backlog #94): `GET`/`POST /api/v1/narasi/kasus`, `POST .../search`, `GET .../{id}` (kasus + versi terbaru + tautan sumber), `GET .../{id}/riwayat`, dan `POST .../{id}/revisi` (versi `REVIEWER_EDIT`, status kasus menjadi `TEAM_REVIEW`; hash sumber dicocokkan server). Hanya grup `tim-kajian` (admin tidak otomatis lolos); tulis memakai `Idempotency-Key`. Hanya kasus `F1_FORMAL` nonpribadi yang dibuka (422 `narasi_jenis_belum_dibuka`/`narasi_sensitif_belum_dibuka`); lingkup ganda 409 `narasi_lingkup_ganda`, `supersedes_id` basi 409 `versi_basi`. Aktor selalu dari token. Tidak ada PATCH/DELETE; tidak ada migrasi; `FEATURE_AI_NARRATIVE_DRAFT` tidak berubah.
- **Tabel kasus narasi dan versinya, append-only** (backlog #92): tabel `narasi_kasus` (UNIQUE delapan kolom lingkup, `NULLS NOT DISTINCT`), `narasi_versi` (`revision_no` > 0 unik per kasus, `ai_run_id` unik) dan `narasi_versi_sumber`, revisi `74125eebc244`. Trigger `narasi_tolak_ubah()` membuat basis data menolak UPDATE/DELETE pada `narasi_versi` dan `narasi_versi_sumber`. Enum `NarrativeKind`, `StatusNarasi` (14 nilai), `RevisionOrigin`, `BasisRelation` di `narasi/schemas/kasus.py`. Belum ada rute atau service; tidak ada perubahan yang terlihat pengguna.
- **Gateway dan worker job AI dengan karantina** (backlog #90): `ai/gateway.py` (`AiGateway.ajukan`, `FungsiAi`, `FUNGSI_TERDAFTAR` kosong), `ai/guardrail.py` (`GUARDRAIL_V1`, aturan PRM:6) dan `ai/worker.py` (`python -m anjab_abk_backend.ai.worker`). Alur gerbang PII per sumber -> `ai_run` -> model tanpa alat -> validasi keluaran -> karantina; sumber kosong atau metadata hilang menjadi `EVIDENCE_GAP`, masukan berPII `DIBLOKIR`, kegagalan apa pun berakhir `MANUAL_REVIEW`. Hanya tabel `ai_run` dan `async_job` yang ditulis. Env baru `AI_WORKER_POLL_DETIK` (5) dan `AI_JOB_MAKS_PERCOBAAN` (3). Tidak ada rute HTTP baru, registri fungsi produksi kosong, dan `FEATURE_AI_NARRATIVE_DRAFT` tetap `false`; worker keluar bila flag mati.
- **Klien model Claude** (backlog #89): `ai/klien.py` dengan Protocol `KlienModel`, `AnthropicKlienModel` (SDK `anthropic`, structured output `json_schema`, thinking adaptive, tanpa `tools`/sampling/retry, fallback penolakan server-side), `JawabanModel`, dan galat `KesalahanModelSementara`, `KesalahanModelPermanen`, `KunciModelTidakAda`. Dependensi baru `anthropic>=2.4,<3`. Env baru `AI_MODEL` (bawaan `claude-opus-5-5`), `AI_EFFORT` (`high`), `AI_MAX_TOKENS` (`16000`), `AI_TIMEOUT_DETIK` (`300`), `AI_INFERENCE_GEO` (kosong), `AI_REFUSAL_FALLBACK` (`true`); kunci dibaca SDK dari `ANTHROPIC_API_KEY`. Belum ada pemanggil; `FEATURE_AI_NARRATIVE_DRAFT` tetap `false`.
- **Kill switch layanan AI tanpa restart** (backlog #88): tabel `ai_saklar_event` (revisi `e4b8c1d6a2f9`, append-only), seam `SaklarAiService`, fungsi `ai_boleh_jalan` (`FAIL CLOSED`), serta `GET /api/v1/system/ai/saklar`, `POST /api/v1/system/ai/saklar/matikan` dan `/hidupkan` (admin saja, body `{alasan}` min. 5 karakter, `Idempotency-Key`, aksi berulang 409, aktor dari token). `hidupkan` tidak menyalakan flag env `FEATURE_AI_NARRATIVE_DRAFT`; rute lain tidak digerbang saklar. Belum ada pemanggilan model.
- **Pemeriksa keluaran model** (backlog #87): `ai/keluaran.py` dengan `skema_dengan_amplop` (amplop `source_refs`, `cited_spans`, `confidence_reason`, `unknowns`, `contradictions`, `human_review_required=true`) dan `cek_keluaran` yang memutuskan `LOLOS`, `EVIDENCE_GAP`, atau `KARANTINA` berikut kode alasan (`JSON_TIDAK_SAH`, `SKEMA_TIDAK_SAH`, `SUMBER_FIKTIF`, `HASH_TIDAK_COCOK`, `KUTIPAN_TIDAK_DITEMUKAN`, `TANPA_SITASI`, `KUTIPAN_KOSONG`, `GAP_TANPA_ALASAN`). Dependensi baru `jsonschema`. Belum ada pemanggilan model.
- **Gerbang redaksi PII dan daftar izin sumber sebelum model** (backlog #86): paket `ai/` dengan `periksa_pii`, `gerbang_masukan`, dan `muat_kamus_nama`. Bawaan paling ketat: hanya jenis `SINTETIS` lolos dan temuan PII apa pun menolak masukan. Env baru `AI_JENIS_SUMBER_DIIZINKAN` (bawaan `["SINTETIS"]`) dan `AI_PII_MODE` (`BLOKIR`/`SAMARKAN`). Nama di luar kamus hanya tertangkap lewat pola konteks. Belum ada pemanggilan model.
- **Register run AI** (backlog #85): tabel `ai_run` (revisi `d7a2f4c9e1b3`), seam `AiRunService`, helper `hash_masukan` dan `bangun_protocol_id`, serta `GET /api/v1/system/ai/runs` dan `GET /api/v1/system/ai/runs/{run_id}` (admin saja, tanpa `masukan` dan `keluaran`). Env baru `AI_PROTOCOL_ARM` (bawaan `TANPA_ARM`) dan `AI_SIMPAN_MASUKAN` (bawaan `false`; `masukan` dikosongkan saat run ditutup). Belum ada pemanggilan model.
- **Pembanding revisi skema basis data** (backlog #84): `GET /api/v1/system/skema` (admin saja, `operation_id` `system_skema_get`) mengembalikan `SkemaDbRead` dengan `revisi_db`, `head_kode`, `selaras`, `selisih_model`, dan `selisih_terbaca`. Hanya baca; `GET /api/v1/version` tidak berubah.
- **Image `linux/arm64`** (backlog #83): `release.yml` kini menerbitkan image `linux/amd64` dan `linux/arm64`; target `make test-arm64` dan job CI `arm64` (runner `ubuntu-24.04-arm`) membangun image runtime lalu memastikan `aarch64`, impor `psycopg`, dan `pg_dump` versi 16. Tidak ada perubahan kode aplikasi.
- **Distribusi rating OPM per task** (backlog #82, A29): `OpmHasilTaskRead` memuat `min_`/`median_`/`max_` untuk `importance`, `frequency`, `criticality` (`float | null`) dan `rating_spread` (`bool | null`, true bila max - min >= 2 pada minimal satu dimensi); semuanya `null` bila `n == 0`. `mean_*`, `sd_*`, dan flag esensial tidak berubah.
- **Commit build pada `GET /api/v1/version`** (backlog #79): respons kini memuat `commit` (SHA build image, `unknown` bila dibangun di luar `release.yml`). `release.yml` meneruskan `GIT_COMMIT` lewat `build_args`; `Dockerfile` menyetel `APP_BUILD_COMMIT`.
- **Kunci optimistik dan Idempotency-Key di rute tulis modul redesain** (backlog #77, A5):
  seluruh `PATCH` redesain (masalah, penilaian, bukti, alternatif, konteks, versi metode, cakupan
  jabatan, kode orang, sesi, proses, langkah, konfirmasi) menerima `If-Match` (412 bila usang,
  428 bila `REQUIRE_IF_MATCH=true` dan header absen, tanpa entri riwayat baru); GET sumber dan
  respons sukses mengembalikan `ETag`. Seluruh `POST` non-search (pembuatan, aksi
  status/putuskan/kunci-cerita/tampilkan-dugaan/kirim/ralat/angkat-masalah, langkah, koreksi)
  menerima `Idempotency-Key`: key sama diulang mengembalikan 200 dengan respons pertama (satu
  baris, satu riwayat), key yang masih diproses 409. Tanpa header perilaku tidak berubah.
  Endpoint baru: `GET /api/v1/redesain/langkah/{langkah_id}` (sumber ETag untuk `PATCH` langkah).
- **Kunci optimistik dan Idempotency-Key di rute tulis OPM dan Task Inventory** (backlog #76, A5):
  `PATCH`/`PUT`/`DELETE` pada sesi, responden, jawaban draft OPM, seleksi dan detail TI, serta
  hapus usulan menerima `If-Match` (412 bila usang, 428 bila `REQUIRE_IF_MATCH=true` dan header
  absen); GET sumbernya dan respons sukses penulisan mengembalikan `ETag`. Rute `POST` non-search
  (buka/tutup/mulai-tahap, buat dan alihkan responden, bulk, submit seleksi/detail/jawaban,
  keputusan Tahap 2, usulan, analisis, purge/reseed katalog) menerima `Idempotency-Key`: key sama
  diulang mengembalikan 200 dengan respons pertama, key yang masih diproses 409. Tanpa header,
  perilaku tidak berubah. Endpoint baru: `GET /api/v1/task-inventory/usulan/{usulan_id}`
  (sumber ETag untuk `DELETE`).
- **Penyimpanan dan mesin status job asinkron** (backlog #78): tabel `async_job`, status `PENDING/RUNNING/SUCCEEDED/FAILED/MANUAL_REVIEW` dengan aturan transisi, seam `AsyncJobService`, dan endpoint admin `GET /api/v1/system/jobs/{job_id}`. Belum ada produsen job.
- **Skor WCP/DCS di balik flag `WCP_DCS_SCORING`** (backlog #75, A7): selama flag mati (bawaan),
  `POST /api/v1/{wcp,dcs}/analisis` dan `GET /api/v1/{wcp,dcs}/hasil` mengembalikan `mode: "RAW_ONLY"`
  berisi frekuensi jawaban raw dan `mean_raw`/`sd_raw` per item, tanpa skor dimensi/sub-skala,
  interpretasi, `risk_flag`, alpha, maupun K-Index. `GET .../hasil-responden/{id}` menjawab 409
  `scoring_key_not_approved`. Saat flag hidup isi tetap seperti sebelumnya ditambah `mode: "SCORED"`.
  Batas `min_responden` tetap berlaku di kedua mode.

- **Log audit baca data terlindung** (backlog #74, A5): setiap `GET` yang lolos guard object-level
  (`authorize_responden_access`/`authorize_sesi_access`/`authorize_opm_sesi_access`) dan seluruh
  `GET` `/api/v1/redesain/kode-orang` & `/api/v1/redesain/ekspor` menulis satu record `protected_read`
  di logger `anjab_abk_backend.audit` berisi `actor`, `resource`, `resource_id`, `tujuan`. Tujuan
  diambil dari header opsional `X-Tujuan-Akses` (maks. 200 karakter; absen -> `TIDAK_DINYATAKAN`).
  Penolakan 403 dan operasi tulis tidak dicatat; nama/isi data tidak pernah masuk log.

- **Kunci optimistik & idempotensi rute tulis WCP/DCS** (backlog #73, A5): `PATCH` instrumen & item,
  `PUT` jawaban draft, `DELETE` item & responden menerima `If-Match` (412 bila usang; 428 bila
  `REQUIRE_IF_MATCH=true` dan header absen); `GET` instrumen, item (endpoint baru
  `GET .../items/{item_id}`), responden, dan jawaban mengembalikan header `ETag`. `POST` assign
  responden, submit jawaban, tutup, buka-ulang, analisis, dan reset menerima `Idempotency-Key`
  (ulangan → 200 respons tersimpan; sedang diproses → 409). `WcpItemUpdate`/`DcsItemUpdate`
  menolak field asing (422). Tanpa header, perilaku tidak berubah. Helper bersama:
  `etag.check_if_match`, `api/concurrency.py` (`run_idempotent`).
- **Integritas bank item WCP/DCS** (backlog #72, A8/A30): `WcpItemRead`/`DcsItemRead` bertambah
  `status_paket` (`SAMA` | `REDAKSI_BEDA` | `TIDAK_ADA_DI_PAKET` terhadap CSV paket R1.1) dan
  `kembar_dengan` (mis. `DCS:C8a`); `WcpInstrumenRead`/`DcsInstrumenRead` bertambah
  `item_bank_hash`, `jumlah_item`, `jumlah_redaksi_beda`, `jumlah_tidak_di_paket`; responden
  mencatat `item_bank_hash` bank yang berlaku saat submit final (null untuk draft dan responden
  lama). Teks item tidak diubah. Migrasi `b3e8f1c5a7d2` (dua kolom nullable).

### Diubah

- **Jawaban tersimpan tidak bisa lagi dihapus/ditimpa** (backlog #71, A27 minimum): `POST
  /api/v1/{wcp,dcs}/instrumen/reset`, `PATCH` dan `DELETE .../items/{item_id}` kini ditolak 409
  `instrument_has_responses` bila instrumen sudah berisi >= 1 jawaban (draft maupun submit);
  `POST /api/v1/task-inventory/catalog/purge` ditolak 409 `catalog_in_use` bila masih ada sesi TI
  atau sesi OPM. `POST .../instrumen/buka-ulang` kini juga sah dari `ANALYZED` (non-destruktif,
  jawaban tetap utuh). Tanpa migrasi.

### Ditambahkan

- **Register pengecualian TI-OPM** (backlog #69): tabel `opm_sesi_pengecualian` (migrasi
  `a9c4e7b2d6f1`) mencatat `TI_DETAIL_UNMATCHED`, `OPM_STD_MISSING`, `OPM_RATING_MISSING` tanpa
  mengisi nilai otomatis. Endpoint admin `GET /api/v1/opm/sesi/{sesi_id}/pengecualian`;
  `OpmSesiRead` bertambah `status_verifikasi` (`VERIFIED`/`UNVERIFIED`) dan `jumlah_pengecualian`;
  `OpmHasilTaskRead`: `mean_*` dan flag esensial kini `null` bila `n == 0`, plus field `orphan`.
- **Kerangka feature flag** (backlog #68): lima flag fungsional (`FEATURE_AI_NARRATIVE_DRAFT`,
  `FEATURE_PARTICIPANT_VALIDATION`, `FEATURE_WCP_DCS_SCORING`, `FEATURE_RESEARCH_EXPORT`,
  `FEATURE_CHANGE_AUTHORIZATION`), default mati, serta endpoint baca bertoken
  `GET /api/v1/system/fitur`. Dependency `require_fitur` menolak fungsi yang mati dengan 409
  `feature_disabled`. Tanpa migrasi.

## [0.48.1] - 2026-11-02

### Diperbaiki

- **Sebaran-K tidak lagi membuang versi terkirim saat ralat masih draf** (backlog #66):
  `GET /api/v1/redesain/masalah/{id}/sebaran-k` kini menganggap sebuah konfirmasi digantikan
  hanya bila penggantinya berstatus `terkirim`; selama ralat masih draf, versi terkirim
  sebelumnya tetap dihitung. Skema respons tidak berubah, tanpa migrasi.
- **Search masalah redesain menerima `id`** (backlog #67): `POST /api/v1/redesain/masalah/search`
  kini mengizinkan field `id` di domain dan order (mis. `[["id","in",[...]]]`), sehingga halaman
  agenda yayasan tidak lagi 422 `not_allowed`. Tanpa migrasi.

## [0.48.0] - 2026-11-01

### Ditambahkan

- **Ekspor register XLSX 14 sheet** (backlog #65, butir BE-11b): `GET
  /api/v1/redesain/ekspor/register.xlsx` (`tim-kajian`) mengunduh satu workbook bernama dan
  berurutan seperti paket v1.3 (header baris 4, data mulai baris 5, urut kode), berisi nilai
  tanpa rumus dan hanya kode orang (tidak pernah nama/email). Konfirmasi versi yang digantikan
  diberi awalan `[digantikan]` pada catatan independensi; sheet MULAI, RUBRIK, UJI_RUMUS hanya
  berisi judul dan penunjuk ke paket metode. Dependensi baru: `openpyxl`.
- **Log versi metode redesain** (backlog #64, butir BE-11a): tabel `redesain_versi_metode`
  (migrasi `d7a3b5e9f2c4`, unik `versi`+`bagian`) berisi 5 catatan perubahan metode v1.3
  (sheet PERUBAHAN) hasil seed idempoten. Endpoint khusus `tim-kajian`:
  `GET/POST /api/v1/redesain/versi-metode`, `POST .../search` (field `versi`, `bagian`),
  `GET/PATCH .../versi-metode/{id}`; pasangan ganda 409, tanpa DELETE, perubahan tercatat di riwayat.

- **Ekspor DOCX redesain** (backlog #63, butir BE-10b): dependensi `python-docx>=1.1,<2.0`; modul
  `redesain/ekspor_docx.py` membangun dokumen dari kode. Endpoint khusus `tim-kajian`:
  `GET /api/v1/redesain/ekspor/ringkasan-yayasan/{masalah_id}` (satu halaman),
  `GET .../ekspor/ringkasan-yayasan?status_penilaian=Siap untuk telaah yayasan` (satu berkas,
  satu masalah per halaman, urut kode; tanpa hasil 404), dan
  `GET .../ekspor/lembar-konfirmasi/{masalah_id}` (bagian A terisi, B-E kosong). Isi ringkasan
  hanya dari read-model yayasan: tanpa nama orang maupun isi konfirmasi per orang.

- **Ringkasan yayasan redesain** (backlog #62, butir BE-10a): read-model `RingkasanYayasanRow`
  (sheet YAYASAN) dihitung langsung dari masalah LEFT JOIN penilaian, tanpa tabel/migrasi baru.
  Endpoint khusus `tim-kajian`: `GET /api/v1/redesain/yayasan`, `POST .../yayasan/search`
  (field `konteks_kode`, `status_bukti`, `saran_otomatis`, `prioritas_final`, `status_penilaian`),
  `GET .../yayasan/{masalah_id}`. Masalah tanpa penilaian tetap muncul dengan field penilaian
  `null`; `pemutus` = kode orang + jabatan (tanpa nama); tanpa isi konfirmasi per orang.
- **Cakupan jabatan redesain** (backlog #61, butir BE-9c): tabel `redesain_cakupan_jabatan`
  (satu baris = entri x cabang, pasangan `role_kode`+`cabang` unik; migrasi `c6f9a2d4e8b1`),
  ter-seed 19 jabatan awal J-01..J-19 x {Bandung, Semarang} = 38 baris (`jabatan_id` NULL).
  Endpoint `tim-kajian` `GET/POST /api/v1/redesain/cakupan-jabatan`, `POST .../search`
  (`role_kode`, `cabang`, `status_unit`, `jabatan_id`), `GET/PATCH .../{id}`. Tim memetakan entri ke
  master jabatan secara manual lewat `jabatan_id` (tak dikenal -> 422); pasangan ganda -> 409.
- **Sesi partisipasi redesain** (backlog #60, butir BE-9b): tabel `redesain_sesi` (satu baris =
  satu orang x satu sesi, pasangan `kode_sesi`+`kode_orang` unik) dan `redesain_sesi_masalah`
  (migrasi `b5e8f1c3d7a2`). Endpoint `tim-kajian` `GET/POST /api/v1/redesain/sesi`,
  `POST .../search` (`kode_sesi`, `kode_orang`, `jenis_kegiatan`, `status_izin`),
  `GET/PATCH .../sesi/{id}` (`masalah_ids` ganti-penuh), dan read-model
  `GET .../sesi/rekap-orang` (jumlah sesi berbeda + total menit rencana/disepakati per orang; NULL
  diabaikan, semua NULL -> null). `status_izin` hanya informasi dan tidak memblokir apa pun
  (termasuk `Tidak diotorisasi`). Pasangan ganda -> 409; menit negatif, kode orang/PIC, sekolah,
  atau masalah tak dikenal -> 422. Bukan Time Study.
- **Alternatif redesain** (backlog #59, butir BE-9a): tabel `redesain_alternatif` (migrasi
  `a9d4c6e2b8f3`) dan endpoint `tim-kajian` `GET/POST /api/v1/redesain/alternatif`,
  `POST .../search` (`masalah_id`, `opsi`, `status_telaah`), `GET/PATCH .../alternatif/{id}`.
  Kode `U-001` dst.; pihak asal/penerima berupa jabatan (divalidasi lewat seam anjab, tak dikenal
  -> 422). `status_telaah` (default `Belum ditelaah`) hanya berubah lewat payload eksplisit dan
  tidak pernah diturunkan dari prioritas penilaian. `Alihkan tugas bersyarat` mewajibkan penerima;
  `Uji disetujui terpisah` mewajibkan `keputusan` dan `pemutus_kode_orang` (juga dicek pada PATCH).
- **Prioritas final beralasan, status penilaian, agenda yayasan, sebaran K** (backlog #58, butir
  BE-8b): migrasi `d8a3e5b7c9f2` menambah kolom keputusan pada `redesain_penilaian`.
  `POST /api/v1/redesain/penilaian/{id}/putuskan` (tim-kajian) mencatat prioritas final, alasan
  (selalu wajib), pemutus (kode orang + jabatan), dan tanggal (tidak di masa depan, acuan WIB);
  `PenilaianRead.peringatan` memuat `PRIORITAS_TANPA_BUKTI` / `BERBEDA_DARI_SARAN` (tidak
  memblokir). `POST .../{id}/status` mengatur empat status selain `Telah diputuskan`.
  `GET .../penilaian/agenda-yayasan` memuat penilaian berstatus `Siap untuk telaah yayasan`;
  `GET /api/v1/redesain/masalah/{id}/sebaran-k` menghitung jawaban K1-K4 konfirmasi terkirim
  yang belum digantikan ralat (tanpa skor).
- **Penilaian redesain + saran triase otomatis** (backlog #57, butir BE-8a): tabel
  `redesain_penilaian` (migrasi `c7f2a9d4e1b3`, satu penilaian per masalah) dan endpoint
  `tim-kajian` `GET/POST /api/v1/redesain/penilaian`, `POST .../search`
  (`masalah_id`, `status_bukti`, `saran_otomatis`), `GET/PATCH .../penilaian/{id}`. Masalah yang
  sudah berpenilaian → 409. `saran_otomatis` (P0/K/P1/P2/P3) dihitung ulang setiap create/update
  oleh fungsi murni `redesain.triase.hitung_saran` (port rumus workbook `PENILAIAN!J5`, aturan
  `v1.3`, diuji 13 kasus UJI_RUMUS); bila dikirim di payload, `saran_otomatis`/
  `versi_aturan_triase` diabaikan. Perubahan dicatat di riwayat (`entitas="penilaian"`). Tidak
  ada DELETE.
- **Bukti redesain** (backlog #56, butir BE-7): tabel `redesain_bukti` (migrasi `b6e1d9f4a2c7`)
  dan endpoint `tim-kajian` `GET/POST /api/v1/redesain/bukti`, `POST .../search`,
  `GET/PATCH .../bukti/{id}`. Bukti berkode `B-NNNN`, berupa rujukan teks per klaim (tanpa
  unggah berkas), opsional menunjuk satu langkah ALUR milik proses masalah yang sama (selain itu
  422); pembuat/pemeriksa dirujuk lewat kode orang yang harus dikenal (422). Kosakata baru
  `JenisBukti` dan `StatusPemeriksaanBukti` (default `Belum diperiksa`); perubahan dicatat di
  riwayat (`entitas="bukti"`). Tidak ada DELETE.
- **Ralat konfirmasi, daftar Tim, angkat masalah baru, dan isian luring** (backlog #55, butir
  BE-6b): kolom `redesain_masalah.sumber_konfirmasi_id` (migrasi `a5d8c3e7b2f9`).
  `POST /api/v1/redesain/konfirmasi/{id}/ralat` (`sekolah-pengisi` pemilik) membuat draf versi
  baru yang menautkan versi lama lewat `menggantikan_id` tanpa mengubah yang lama;
  `GET .../konfirmasi/saya` memuat seluruh versi milik pemanggil. `tim-kajian` mendapat
  `GET .../konfirmasi`, `POST .../konfirmasi/search` (respons memuat `digantikan`),
  `POST .../konfirmasi/{id}/angkat-masalah` (membuat masalah `Keterangan kasus` untuk sekolah
  konfirmasi) dan `POST .../konfirmasi/luring` (isian kertas, langsung `terkirim`, membekukan
  status awal dan menandai eskalasi seperti `kirim`). `MasalahRead` bertambah `eskalasi_pada` dan
  `sumber_konfirmasi_id`; `eskalasi_pada` menjadi field search masalah.
- **Fondasi domain Redesain Pekerjaan** (backlog #48, pelacak `ypii-support#424`, butir BE-1):
  paket `redesain/` dengan kosakata baku (`Gelombang`, `StatusAwal`, `StatusBukti`,
  `StatusLangkah`, `Skala`, `Indikasi`, `YaTidak`), dua grup peran baru `tim-kajian` dan
  `sekolah-pengisi` beserta guard `require_tim_kajian` dan `authorize_sekolah_scope`
  (grup `admin` TIDAK otomatis mendapat akses data redesain), tabel `redesain_riwayat`
  append-only (migrasi `d2f7e45a1e23`), serta endpoint baca khusus `tim-kajian`:
  `GET /api/v1/redesain/riwayat` dan `POST /api/v1/redesain/riwayat/search`.
  Grup Authentik terkait perlu dibuat admin di IdP.
- **Kode orang (pseudonim) Redesain** (backlog #49, butir BE-2): tabel `redesain_kode_orang`
  beserta sequence `redesain_kode_orang_seq` (migrasi `05fdd35204c5`) yang memberi tiap orang
  kode stabil `O-0001`, dan peta kode ke partisipan yang hanya terbaca `tim-kajian`
  (`GET/POST /api/v1/redesain/kode-orang`, `POST .../search`, `GET/PATCH .../{id}`; tanpa
  DELETE). `GET /api/v1/redesain/kode-orang/saya` (grup `tim-kajian` atau `sekolah-pengisi`)
  mengembalikan `{kode}` milik pemanggil tanpa `partisipan_id`. Dependency
  `get_kode_orang_pemanggil` menjadi sumber `pelaku_kode_orang` bagi riwayat.
- **Alur untuk sekolah & koreksi langkah** (backlog #54, butir BE-5b): tabel append-only
  `redesain_koreksi_langkah` (migrasi `f4c7d2a9b6e1`). `GET /api/v1/redesain/konfirmasi/{id}/alur`
  (`sekolah-pengisi` pemilik) menampilkan proses sekolah & masalah konfirmasi itu beserta
  langkahnya, hanya setelah dugaan ditampilkan (sebelumnya 409 `DUGAAN_BELUM_DITAMPILKAN`).
  `POST /api/v1/redesain/langkah/{id}/koreksi` menyimpan koreksi per langkah tanpa mengubah
  langkah (pengisi wajib `konfirmasi_id` miliknya; `tim-kajian` boleh tanpa), dan
  `GET .../koreksi` (hanya `tim-kajian`) membacanya terurut waktu. Tanpa PATCH/PUT/DELETE.
- **Alur redesain: proses & langkah** (backlog #52, butir BE-5a): tabel `redesain_proses`
  dan `redesain_langkah` (migrasi `c5d9f13a7b42`). Tim Kajian mencatat proses per
  masalah × sekolah berkode global `P-001` beserta langkahnya berkode `P-001-S01`, `-S02`, …
  dengan status langkah baku (`StatusLangkah`, termasuk "Diperkuat untuk klaim" dan
  "Tidak berlaku"). Endpoint khusus `tim-kajian`: `GET/POST /api/v1/redesain/proses`,
  `POST .../search` (field `masalah_id`, `sekolah_id`, `kode`), `GET/PATCH .../{id}`
  (detail memuat `langkah` terurut `urutan`), `POST .../{id}/langkah`, dan
  `PATCH /api/v1/redesain/langkah/{id}`; tanpa DELETE. Sekolah proses wajib sama dengan
  sekolah masalah bila masalah sudah bersekolah (selisih → 422). Setiap create/update
  dicatat di riwayat (`entitas="proses"`/`"langkah"`).
- **Konfirmasi sekolah redesain** (backlog #53, butir BE-6a): tabel `redesain_konfirmasi` dan
  kolom `redesain_masalah.eskalasi_pada` (migrasi `e3b9a6c2f1d8`). Pengguna grup
  `sekolah-pengisi` mengisi sendiri konfirmasi masalah sekolahnya dengan urutan yang
  ditegakkan sistem: `GET /api/v1/redesain/sekolah/masalah` (masalah yang dibuka, tanpa
  `rumusan_hipotesis`), `POST /api/v1/redesain/konfirmasi` (draf), `PATCH .../{id}`,
  `POST .../{id}/kunci-cerita`, `POST .../{id}/tampilkan-dugaan` (rumusan hipotesis baru
  terbuka setelah cerita dikunci; sebelumnya 409 `CERITA_BELUM_DIKUNCI`), dan
  `POST .../{id}/kirim` (wajib `peran`, `kesesuaian`, `k1`…`k4`, `indikasi_risiko`).
  `GET .../{id}` untuk pemilik atau `tim-kajian` (field `dugaan_diperlihatkan`). Penilaian
  bagian C–E baru bisa diisi setelah dugaan tampil (`DUGAAN_BELUM_DITAMPILKAN`), cerita tak
  bisa diubah setelah dikunci (`CERITA_SUDAH_DIKUNCI`), dan konfirmasi terkirim tak dapat
  diubah. Kirim membekukan status awal masalah dan, bila `indikasi_risiko="Ada indikasi"`,
  menandai `eskalasi_pada`. Sekolah lain / masalah belum dibuka → 403; tanpa PUT/DELETE.

## [0.47.0] - 2026-09-25

### Ditambahkan

- **Endpoint admin untuk mengalihkan responden TI/OPM ke partisipan lain**
  (backlog #47, asal `ypii-support#73`): `POST /api/v1/task-inventory/sesi/responden/{responden_id}/alihkan`
  dan `POST /api/v1/opm/sesi/responden/{responden_id}/alihkan`. Memindahkan
  kepemilikan satu baris responden (mengubah `partisipan_id`/`nama`) tanpa
  mengisi ulang jawaban — status kirim (`tahap1_submit`/`tahap3_submit`/
  `sudah_submit`) dan timestamp-nya tetap utuh, termasuk untuk sesi TI yang
  sudah TAHAP3 dan sesi OPM yang kuotanya penuh. Body
  `{"dari_partisipan_id": "...", "ke_partisipan_id": "..."}` — `dari_partisipan_id`
  adalah guard eksplisit agar tidak menimpa kepemilikan responden yang salah
  secara diam-diam. Menolak `404` (responden/partisipan tujuan tidak ada),
  `422` (asal=tujuan, responden bukan milik `dari_partisipan_id`, atau
  partisipan tujuan nonaktif), `409` (partisipan tujuan sudah jadi responden
  di sesi yang sama).

## [0.46.0] - 2026-09-09

### Diubah

- **Auto-populate responden & koordinator sesi Task Inventory kini menyaring
  cabang** (backlog #41, lanjutan #37/#40). Sebelumnya `SqlTiSesiService.create()`
  mencari SME panel hanya lewat `jabatan_id` lalu meng-assign SELURUH anggotanya
  sebagai responden tanpa menyaring cabang — karena satu panel dipakai kedua
  cabang, sesi Bandung dan Semarang untuk jabatan yang sama mendapat daftar
  responden identik (audit produksi 2026-09-08: 7/7 sesi TI tercampur).
  `assign_ti_responden_banyak()` bertambah parameter `cabang`: partisipan yang
  cabang sekolahnya diketahui dan berbeda dilewati (`BulkAssignResult.skipped`
  beralasan baru `beda_cabang`), partisipan bercabang sama atau tidak diketahui
  tetap masuk ("tidak tahu ≠ salah"). `POST .../sesi/{id}/responden`
  (single-add) dan `POST .../sesi` (create, termasuk `koordinator_id`)/`PATCH
  .../sesi/{id}` kini menolak `422` untuk kombinasi cabang yang diketahui dan
  berbeda.
- **Pewarisan `koordinator_id` sesi dari `SMEPanelModel.koordinator_id`
  dihentikan** (backlog #41, keputusan pemilik proses: koordinator ditentukan
  di sesi, bukan di master data SME panel) — `koordinator_id` kini murni
  berasal dari payload `POST .../sesi`. `SMEPanelModel.koordinator_id` sendiri
  **tidak dihapus** dari model maupun DB, hanya berhenti dibaca jalur ini.
- **Gerbang cabang di atas HANYA berlaku di jalur penambahan** (`create()`/
  auto-populate) — `mark_tahap1()`, `mark_tahap3()`, `delete()`, dan seluruh
  `list_*`/`get`/`count_*` tidak disentuh: responden beda cabang yang sudah
  terdaftar sebelum revisi ini tetap bisa mengisi & submit seperti biasa.
- Tidak ada migrasi Alembic (skema tidak berubah — `beda_cabang` hanya nilai
  string baru di field `alasan` yang sudah bertipe `str` bebas). Data existing
  yang sudah tercampur **tidak** dibersihkan oleh revisi ini (pekerjaan
  data-ops terpisah, di luar lingkup).

## [0.45.0] - 2026-09-08

### Diubah

- **OPM: draft rating parsial diterima; kelengkapan tiga dimensi digerbang saat
  submit** (backlog #39) — `PUT /api/v1/opm/sesi/responden/{id}/jawaban` tidak lagi
  menuntut `importance`/`frequency`/`criticality` terisi sekaligus; ketiganya boleh
  `null` pada draft dan disimpan apa adanya (kolom `opm_jawaban` jadi nullable,
  migrasi `25dba11a0c55`). Kelengkapan ketiga dimensi kini ditegakkan **hanya** di
  `POST .../jawaban/submit` (422, pesan menyebut `task_kode` yang belum lengkap).
  `GET .../hasil` tidak berubah angkanya — baris parsial disaring sebelum masuk
  agregasi.
- **Draft Tahap 3 Task Inventory kini menerima isian parsial; kelengkapan digerbang
  saat submit** (backlog #38). `PUT .../detail` sebelumnya mewajibkan kelima field
  CalHR (`sumber_bukti`/`kondisi`/`frekuensi_teks`/`durasi_per_kali`/`va_type`) penuh
  di setiap baris — partisipan yang menandai 30 tugas dan baru mengisi 10 kehilangan
  seluruh progres karena draft-save ikut ditolak `422`. Kelima field itu kini
  `| None` (opsional) di `TiDetailItem`/`TiDetailRead` dan kolom `ti_detail`
  terkait (migrasi `983594126c4a`); `PUT .../detail` menyimpan `null` apa adanya,
  termasuk saat menimpa nilai yang sebelumnya terisi. `jam_per_minggu` diberi
  `default=0.0` (bukan opsional — field ini memang tidak lagi diisi partisipan).
  Gerbang kelengkapan **baru** ada di `POST .../detail/submit`: menolak `422` bila
  ada baris tersimpan dengan salah satu field masih `null`, pesan menyebut
  `task_kode`-nya. `compute_hasil_sesi` (dipakai `GET .../hasil`) mengabaikan entri
  parsial dari `fmean`/`va_type_dist`/`n_detail` agar draft yang belum di-submit
  tidak mencemari agregasi ABK.

## [0.44.0] - 2026-08-05

### Ditambahkan

- **Sesi OPM dipisah per cabang** (backlog #37, menyerap #18) — kolom baru
  `opm_sesi.cabang`, DITURUNKAN dari `ti_sesi.cabang` sesi Task Inventory sumber saat
  sesi OPM dibuat (`OpmSesiCreate`/`Update` tidak berubah, tetap `extra="forbid"`;
  payload yang mengirim `cabang` tetap `422`). Sebelumnya `opm_sesi.jabatan_id` unik
  secara global, sehingga jabatan yang punya sesi TI Bandung *dan* Semarang mustahil
  dibuatkan dua sesi OPM berdampingan — `unique=True` itu dilepas, diganti uniqueness
  `(jabatan_id, cabang)` yang ditegakkan di lapisan aplikasi (bukan constraint DB,
  karena `cabang` nullable). Pesan `409` kini menyebut **nama** jabatan + cabang
  (`"Sesi OPM untuk jabatan 'Guru BK' cabang 'Bandung' sudah ada."`), bukan ID mentah.
  **Sumber auto-populate responden berpindah** dari seluruh anggota SME panel menjadi
  responden sesi TI sumber yang sudah submit Tahap 1 — `max_responden` kini
  dibandingkan ke himpunan submitter itu, bukan ke ukuran panel. `cabang`
  (`OpmSesiRead`) dan `sesi_cabang` (`OpmKuesionerItemRead`)/`cabang`
  (`OpmHasilSesiRead`) ditambahkan additive, ikut `SEARCHABLE_FIELDS`. Dua revisi
  Alembic: DDL (`981b2e1945b0`) lalu backfill data (`5f9c20955d88`, mengisi `cabang`
  3 sesi OPM produksi YPII dari `ti_sesi.cabang` sumbernya — semuanya Semarang, tanpa
  menghapus satu baris pun). Klien (web app `anjab-abk-web-app#54`, MCP
  `anjab-abk-mcp#10`) menyusul setelah kontrak ini live.

- **Batalkan freeze Tahap 3 sesi Task Inventory (`TAHAP3` → `TAHAP2`)** (backlog #35) —
  endpoint baru `POST /api/v1/task-inventory/sesi/{sesi_id}/batalkan-tahap3` (admin-only,
  body `{"alasan": "<min 1 karakter>"}`). Sebelumnya `mulai-tahap3` membekukan himpunan
  task secara permanen tanpa jalan keluar: sesi yang ter-freeze prematur (mis. Tahap 1
  baru sebagian responden submit) hanya bisa dihapus lalu dibuat ulang, kehilangan
  seluruh seleksi Tahap 1 & keputusan koordinator Tahap 2. Endpoint ini menghapus baris
  `ti_sesi_task_terpilih` sesi tersebut, mengembalikan `task_frozen` ke `false` dan
  `status` ke `TAHAP2` — **tanpa** menyentuh `ti_responden` (`tahap1_submit`/
  `tahap3_submit` tetap apa adanya), `ti_seleksi`, `ti_detail`, maupun `ti_usulan_task`,
  sehingga sesi dapat dibekukan ulang lewat `mulai-tahap3` dengan data yang sama.
  Setiap pemanggilan dicatat `logger.warning` terstruktur (aktor, sesi, alasan) untuk
  audit, mengikuti pola `paksa=true` pada `delete_sesi`. `422` bila status bukan
  `TAHAP3` atau `alasan` kosong; `403` non-admin; `401` tanpa token; `404` sesi tak
  dikenal. `openapi.json` bertambah satu operasi (`taskinv_sesi_batalkan_tahap3`) —
  breaking-additive; tool MCP `ti_batalkan_tahap3` menyusul di
  `cakrawala-tumbuh/anjab-abk-mcp#9`.

  Catatan kontrak: setelah sesi kembali ke `TAHAP2`,
  `GET /sesi/{id}/task-terpilih` menolak dengan `422` (bukan `200` berisi daftar
  kosong) — endpoint itu sejak awal hanya melayani `TAHAP3`/`CLOSED`/`ANALYZED`, dan
  revisi ini **tidak** mengubah gerbang tersebut.

## [0.43.0] - 2026-07-29

### Ditambahkan

- **Nilai standar OPM dibawa ke snapshot task sesi & respons API** (backlog #34,
  lanjutan #33) — tiga kolom baru `std_importance`/`std_frequency`/`std_criticality`
  (skala 1-5, nullable) pada `opm_sesi_task`, diisi sekali oleh
  `SqlOpmSesiService.create()` dengan MENYALIN nilai dari
  `ti_uraian_tugas_jabatan.std_opm_*` pada saat sesi OPM dibuat — beku, tidak pernah
  disegarkan ulang meski katalog TI berubah setelahnya. Terekspos di
  `GET /api/v1/opm/sesi/{id}/task` (`OpmSesiTaskRead`) sebagai saran nilai awal untuk
  form responden; `POST .../jawaban` & `.../jawaban/submit` tidak berubah — ketiga
  dimensi tetap wajib diisi eksplisit 1-5, nilai standar tidak menggantikan jawaban.
  Task yang kodenya tidak punya nilai standar di katalog (mis. hasil materialisasi
  usulan Tahap 1) mendapat baris snapshot dengan ketiganya `null`, bukan error.

- **Nilai standar OPM (importance/frequency/criticality) di katalog Task Inventory**
  (backlog #33) — tiga kolom baru `std_opm_importance`/`std_opm_frequency`/
  `std_opm_criticality` (skala 1-5, nullable) pada `ti_uraian_tugas_jabatan`, terekspos
  di skema baca/tulis katalog uraian tugas (`UraianTugasCreate`/`Update`/`Read`,
  `TiCatalogRead`, `TiTaskTerpilihRead`). Sumber nilai: sheet `05_Raw_Task_Migration`
  Task Bank (kolom `Importance`/`Criticality`/`Frequency`) — sebelumnya hanya kolom
  lain (`Frequency` teks, `Formal_Actual`, `Baseline_Peak`, `Duration_Estimate`) yang
  ikut termigrasi ke `task_catalog.json`, dua kolom ini terlewat. `task_catalog.json`
  diperbarui in-place (1.138 baris, seluruhnya bernilai `Importance`/`Criticality`;
  15 baris ber-`Frequency` kotor mendapat `std_opm_frequency = null`, tidak ditebak).
  Instance yang sudah berjalan diisi via migrasi data terpisah dari berkas beku
  `migrations/data/20260729_opm_std_values_v2_19.json` (hanya menimpa baris `NULL`,
  baris yang sudah diedit manual tidak tersentuh). Item lanjutan (pemakaian nilai ini
  di modul OPM) di luar lingkup revisi ini.

### Diubah

- **Samakan redaksi 75 baris klon jabatan `Koordinator …` dengan kembarannya di katalog**
  — jabatan `Koordinator Ekstrakurikuler`/`Koordinator Humas`/`Koordinator Sarana
  Prasarana` (nomenklatur cabang Bandung, 124 baris `KOEKS-`/`KOHUM-`/`KOSAR-`) dibuat
  manual di luar `task_catalog.json` dengan menyalin uraian tugas dari jabatan
  kembarannya (`PEK-`/`WKHUM-`/`WKSAR-`), sehingga terlewat oleh penyederhanaan redaksi
  v2.19-R1 (#30): kembarannya sudah disederhanakan, klonnya masih redaksi 5C lama. 75
  baris yang menganga itu kini disamakan lewat migrasi data Alembic `3889bd9af66e`
  (mekanisme sama: hanya menimpa baris yang teksnya masih persis redaksi lama). 49 baris
  klon sisanya kembarannya juga belum disederhanakan, jadi memang sudah konsisten.
  Ketiga jabatan tetap tidak dimasukkan ke `task_catalog.json` — instalasi baru tetap
  tidak memilikinya (status quo).

## [0.42.2] - 2026-07-28

### Diubah

- **Selaraskan uraian tugas katalog TI dengan redaksi sederhana v2.19-R1** (backlog
  #30) — 740 dari 1.138 task di katalog Task Inventory (`kategori
  Language_Eligibility_Status == ELIGIBLE`) kini memakai redaksi bahasa yang lebih
  sederhana hasil panel bahasa (`Task_Bank_Redaksi_Sederhana_v2_19_R1.xlsx`),
  menggantikan pola 5C asli yang berbelit ("...untuk alasan, cara, menghasilkan
  output"). 398 task yang masih menunggu klarifikasi SME (`SPLIT_REQUIRED`,
  `OUTPUT_UNCLEAR`, dll.) tidak berubah. Instance yang sudah berjalan (mis. pilot
  YPII) ikut diperbarui lewat migrasi data Alembic baru yang hanya menimpa baris
  bertext persis redaksi lama (baris yang sudah diedit manual tidak tersentuh).

## [0.42.1] - 2026-07-26

### Diperbaiki

- **Tolak responden ganda per partisipan di satu sesi Task Inventory** (backlog #29)
  — `POST /api/v1/task-inventory/sesi/{id}/responden` kini menolak `409` bila
  `partisipan_id` sudah terdaftar sebagai responden di sesi itu (pesan:
  "Partisipan ini sudah terdaftar sebagai responden pada sesi ini."). Endpoint
  bulk (`.../responden/bulk`) tidak berubah (tetap `skipped: sudah_terdaftar`).
  Ditegakkan juga di lapisan basis data lewat
  `UniqueConstraint("sesi_id", "partisipan_id")` (`uq_ti_responden_sesi_partisipan`)
  pada `ti_responden`; `partisipan_id` NULL (responden manual) tetap boleh
  berulang. Migrasi baru membersihkan duplikat lama sebelum menambah constraint.

## [0.42.0] - 2026-07-26

### Ditambahkan

- **Review koordinator Tahap 2 memuat usulan Tahap 1 & materialisasi ke katalog**
  (backlog #27) — koordinator kini melihat usulan uraian tugas peserta Tahap 1
  berdampingan dengan task partial di `GET /api/v1/task-inventory/sesi/{id}/tahap2`
  (`TiTahap2ReviewRead.usulan`), dan bisa memutuskannya lewat `POST .../tahap2`
  (`keputusan_usulan`). `jumlah_belum_diputuskan` kini menghitung task **dan**
  usulan yang belum diputuskan. Usulan yang disetujui dimateralisasi otomatis
  menjadi baris katalog `ti_uraian_tugas` berkode `TIU<8 hex>` saat
  `POST .../mulai-tahap3` — `unit` diturunkan dari katalog jabatan yang ada,
  `urutan` melanjutkan urutan tertinggi kombinasi jabatan+unit. Materialisasi
  bersifat sekali jalan (aman dipanggil ulang). Usulan yang ditolak/belum
  diputuskan tidak masuk himpunan final.
- **Entitas & endpoint usulan uraian tugas tambahan peserta Tahap 1** (backlog #26) —
  responden Task Inventory Tahap 1 kini bisa mencatat, melihat, dan menghapus usulan
  uraian tugas baru di bawah tugas pokok/detil tugas pilihannya, saat tugas yang ia
  kerjakan tidak ada di katalog. `POST`/`GET /api/v1/task-inventory/sesi/responden/
  {responden_id}/usulan`, `DELETE /api/v1/task-inventory/usulan/{usulan_id}`. Usulan
  tidak menyentuh katalog master; nama tugas pokok/detil tugas induk diresolusi live
  saat baca. Review koordinator Tahap 2 & materialisasi ke katalog menyusul di item
  terpisah (#27). Tabel baru `ti_usulan_task` (migrasi `92f6851d040c`).

## [0.41.0] - 2026-07-26

### Ditambahkan

- **Endpoint admin `POST /api/v1/system/backup` & `POST /api/v1/system/restore`**
  (backlog 025) — admin (grup Authentik `admin`) kini bisa mengunduh cadangan penuh
  basis data dan memulihkannya lewat API, tanpa akses shell ke server. `backup`
  mengalirkan langsung keluaran `pg_dump --format=custom --no-acl --no-owner`
  (server tidak menyimpan salinan); `restore` menerima unggahan multipart
  (`berkas` + `konfirmasi` yang harus persis sama dengan nama basis data tujuan)
  dan menjalankan `pg_restore --clean --if-exists --no-acl --no-owner
  --single-transaction`. Skema hasil restore **tidak** di-upgrade otomatis — respons
  `RestoreResult.peringatan` memberi tahu bila revisi Alembic berbeda dari head
  aplikasi. Logika baru di `services/backup.py` (`BackupService`); kredensial DB
  dioper lewat environment `PGPASSWORD`, tidak pernah sebagai argumen command line.
  Setting baru `restore_max_body_bytes` (default 512 MiB) mengecualikan path restore
  dari batas ukuran body umum 1 MiB. `Dockerfile`/`Dockerfile.test` kini memasang
  `postgresql-client-16` dari repositori PGDG (produksi memakai PostgreSQL 16;
  paket bawaan Debian bookworm versi 15 tidak kompatibel).

## [0.40.0] - 2026-07-26

### Diubah

- **Task Inventory Tahap 3: submit final menolak `va_type` "Context-Dependent"; `"Needs
  Validation"` dihapus dari `VaType`.** `VaType` (`taskinv/schemas/calhr.py`) kini memuat
  4 nilai (`VA-Core`/`VA-Enable`/`NVA-Residual`/`Context-Dependent`) — `"Needs Validation"`
  dihapus tuntas dari kontrak (0 pemakai; 2 baris seed placeholder ber-`kode`
  `STSAR-ALL-LEAD-026`/`027` yang masih memakainya turut dibersihkan dari
  `data/task_catalog.json`, mengikuti pembersihan yang sama di live DB 2026-07-25).
  `"Context-Dependent"` tetap diterima sebagai prefill katalog & draft (`PUT
  .../detail`), tetapi `POST .../detail/submit` kini ditolak (422) selama masih ada
  entri ber-`va_type` itu — pesan menyebut `task_kode` yang harus dipastikan menjadi
  VA-Core/VA-Enable/NVA-Residual sebelum finalisasi. Diterapkan paritas di seam
  in-memory (`services/detail.py`) dan SQL (`services/detail_sql.py`).
- **Relasi `uraian_tugas` ↔ `jabatan` diubah menjadi m2m via association object**
  (`TiUraianTugasJabatanModel`, tabel `ti_uraian_tugas_jabatan`) — sebelumnya
  `TiUraianTugasModel` menautkan tiap uraian tugas ke tepat satu jabatan lewat
  kolom tunggal `jabatan_id`. Kanonik (`TiUraianTugasModel`) kini hanya memuat
  `id`/`uraian`/`created_at`; kolom per-jabatan (`kode`, `unit`, `jabatan_id`,
  `urutan`, `tugas_pokok_id`, `detil_tugas_id`, `std_*`) pindah ke link. Migrasi
  1:1 non-lossy — belum ada dedup/kanonikalisasi baris `uraian` yang teksnya
  identik (menyusul terpisah). **Kontrak API (`ti_catalog`, CRUD
  `uraian-tugas`, `openapi.json`) tidak berubah** — diverifikasi diff kosong
  sebelum/sesudah refactor; MCP & frontend tidak perlu perubahan.

## [0.39.0] - 2026-07-23

### Diubah

- **Endpoint list "koleksi anak" kini mengembalikan `Page[T]`** (`{items, total,
  limit, offset}`) dengan query `limit` (`ge=1,le=500`, default 20) + `offset`
  (`ge=0`, default 0) dan header `Link` (RFC 5988 first/prev/next/last), seragam
  dengan resource master yang sudah dipaginasi. Terdampak: `GET /dcs/responden`,
  `GET /wcp/responden`, `GET /opm/sesi/{id}/responden`, `GET /opm/sesi/{id}/task`,
  `GET /task-inventory/sesi/{id}/responden`,
  `GET /task-inventory/sesi/{id}/task-terpilih`,
  `GET /task-inventory/sesi/responden/{id}/detail`,
  `GET /task-inventory/catalog` (filter `jabatan_id`/`unit` tetap berlaku, kini
  bertambah `limit`/`offset`), dan `GET /time-study/penugasan/{id}/log`. `total`
  = jumlah SELURUH baris cocok filter (sebelum limit/offset). **Breaking**: klien
  yang membaca array telanjang harus membaca `.items`. Kode status & auth tak
  berubah (404 sesi/penugasan tak ada tetap 404). Helper header `Link` bersama
  diekstrak ke `api/pagination.py`.

## [0.38.0] - 2026-07-21

### Ditambahkan

- **`DELETE /api/v1/dcs/sub-skala/items/{item_id}`** dan
  **`DELETE /api/v1/wcp/dimensi/items/{item_id}`** (admin): hapus satu item dari
  master instrumen DCS/WCP. Hanya sah saat instrumen berstatus `OPEN` (422 bila
  tidak), menolak menghapus item terakhir sebuah sub-skala/dimensi (422), dan
  membersihkan jawaban yatim untuk item tersebut (kolom `*_jawaban.item_id` bukan
  FK sehingga tidak ada cascade DB). 404 bila item tidak ada, 401/403 untuk
  non-admin.

### Diubah

- **Analisis DCS & WCP kini membaca katalog item dari DATABASE**, bukan dari
  konstanta seed (`dcs.seed`/`wcp.seed`). `compute_hasil`/`compute_hasil_responden`
  menerima parameter `catalog` yang dibangun dari `dcs_item`/`wcp_item` (via
  sub-skala/dimensi service). Sebelumnya perubahan katalog lewat API (hapus item,
  atau ubah `arah`/`reverse_type`) DIABAIKAN diam-diam oleh analisis: setiap
  responden yang menjawab jumlah item ≠ jumlah item seed gugur dari agregat
  sub-skala/dimensi (`n_responden` bisa jadi 0 tanpa peringatan). Angka statistik
  untuk katalog utuh (belum ada item dihapus) tidak berubah.
- **Seeding item DCS/WCP menjadi first-run** (`seed_db.py`): bila tabel item sudah
  berisi, seeding item dilewati. Mencegah item yang sengaja dihapus admin muncul
  lagi ("resurrection") saat `initdb` menjalankan seed di tiap boot container.
  Konsekuensi: item baru pada konstanta seed tidak lagi di-top-up ke deployment
  lama — sesuai model "1 instance = 1 studi".

## [0.37.0] - 2026-07-15

### Ditambahkan

- **`POST /api/v1/{dcs,wcp}/instrumen/reset`** (admin): jalur resmi keluar dari
  status `ANALYZED` (terminal) — menghapus SEMUA responden & jawaban instrumen
  (dalam satu transaksi) dan mengembalikan status ke `OPEN`. Sah dipanggil dari
  status apa pun (idempoten). Berbeda dari `/buka-ulang` yang tetap hanya sah dari
  `CLOSED` dan tidak menghapus data (perilaku `/buka-ulang` tidak berubah).
  Menyelesaikan backlog 043 (WCP/DCS produksi terjebak `ANALYZED` oleh data uji
  coba, tanpa jalan buka kembali via API).

## [0.36.0] - 2026-07-15

### Diubah (breaking change)

- **Task Inventory: hapus tuntas `ai_mode` (enum `AiMode`) & `dcs_flag` dari kontrak
  CalHR** (backlog 039). Feedback user (foto, 2026-07-14) pada halaman Tahap 3: dua
  isian "AI mode" dan "Resiko DCS" dihapus dari produk, bukan sekadar disembunyikan
  di UI.
  - **Isian per-entri Tahap 3**: `TiDetailItem.ai_mode`/`.dcs_flag` dan
    `TiDetailRead.ai_mode`/`.dcs_flag` dihapus. `POST/PUT .../detail` kini menolak
    (`422`, `extra="forbid"`) payload yang masih menyertakan salah satu field ini.
  - **Nilai standar master (prefill Tahap 3)**: `std_ai_mode`/`std_dcs_flag` dihapus
    dari `TiCatalogRead`, `UraianTugasCreate`/`Update`/`Read`.
  - **Agregasi hasil analisis**: `ai_mode_dist`/`dcs_flag_count` dihapus dari
    `TiHasilTaskRead`; `std_ai_mode`/`std_dcs_flag` dihapus dari `TiTaskTerpilihRead`.
    `va_type`/`va_type_dist`/`std_va_type` **tidak disentuh**.
  - Enum `AiMode` (`schemas/calhr.py`) **dihapus total** — dipastikan 0 pemakai
    tersisa sebelum dihapus (`grep -rn AiMode src/` → nihil).
  - Model ORM: `TiDetailModel.ai_mode`/`.dcs_flag`, `TiUraianTugasModel.std_ai_mode`/
    `.std_dcs_flag` dihapus. Migrasi Alembic `fd3dd550aa99` (setelah `08b6b999ee05`
    dari backlog 037) men-`DROP COLUMN` keempatnya di `ti_detail` dan
    `ti_uraian_tugas`. **Data lama pada kolom ini hilang permanen** saat migrasi
    dijalankan — baris uji coba TI Teranalisis di produksi YPII kemungkinan
    terdampak; backup DB (`make backup`) wajib sebelum `alembic upgrade head` di
    produksi. `downgrade()` best-effort: kolom `ti_detail.ai_mode`/`dcs_flag`
    (semula `NOT NULL` tanpa default) diberi `server_default` sementara agar
    `ADD COLUMN` tidak gagal di tabel berisi, lalu default dilepas.
  - Klien (web-app, MCP) menyusul di item 040 (blocked-by 039) meregenerasi tipe
    dari `openapi.json` yang berubah.

- **Task Inventory (`TiSesi`): `periode` diganti `cabang`; `min_responden`/
  `max_responden` dihapus total** (backlog 037). Feedback user: sesi TI harus
  terikat ke cabang lokasi (Bandung/Semarang) alih-alih periode bebas teks, dan
  konsep batas atas jumlah responden dicabut — mengikuti keputusan yang sama
  yang sudah diambil untuk DCS/WCP (`[2026-07-12]` di bawah).
  - `TiSesiCreate`/`TiSesiUpdate`/`TiSesiRead`: field `periode` (string bebas
    `YYYY-MM`) diganti `cabang` (`Literal["Bandung", "Semarang"]`, tipe baru
    `CabangSesi`). `TiSesiCreate.cabang` **wajib** (sesi baru selalu punya
    cabang); `TiSesiRead.cabang`/`TiSesiUpdate.cabang` **Optional** — baris
    `ti_sesi` lama (dibuat sebelum revisi ini) punya `cabang = NULL` (TIDAK
    ada backfill otomatis, lihat migrasi).
  - `min_responden`/`max_responden` dihapus dari `TiSesiCreate`/`Update`/`Read`,
    `TiSesiModel`, dan seluruh lapisan responden TI
    (`assign_ti_responden_banyak`, `SqlTiRespondenService.create`/
    `assign_banyak`, endpoint `POST .../responden` & `.../responden/bulk`).
    Aturan 422 "panel SME > max_responden" (backlog 028, entri `[2026-07-14]`
    di bawah) ikut **dibuang** — panel besar kini selalu berhasil membuat
    sesi dengan SELURUH anggota jadi responden, tanpa batas atas.
  - Uniqueness sesi berubah dari `(jabatan_id, periode)` menjadi
    `(jabatan_id, cabang)`.
  - Downstream yang sebelumnya mengekspos `periode` ikut diganti `cabang`:
    `TiHasilSesiRead.periode` → `cabang`, `TiKuesionerItemRead.sesi_periode`
    → `sesi_cabang`.
  - Payload lama yang masih mengirim `periode`/`min_responden`/
    `max_responden` ditolak `422` (`extra="forbid"`) — klien (web-app, MCP)
    perlu menyesuaikan (menyusul: item 038 + audit MCP `buat_ti_sesi`/
    `ti_tambah_responden*`).
  - Migrasi Alembic `08b6b999ee05`: kolom `cabang` ditambahkan
    `nullable=True` **tanpa backfill** (baris produksi lama tetap `NULL`
    sampai admin mengisinya manual — di luar cakupan migrasi ini, data
    transaksi produksi sengaja tidak disentuh). `downgrade()` best-effort
    (mengikuti konvensi `3b10e24fa970`).
  - **`OpmSesi` sengaja tidak disentuh** — field `periode`/`min_responden`/
    `max_responden` paralel di `opm/schemas/sesi.py` tetap ada (item terpisah
    bila diinginkan).

## [0.34.1] - 2026-07-14

### Diperbaiki

- **`POST /api/v1/opm/sesi` tidak lagi selalu gagal dengan 409 "sesi sudah ada" palsu**
  (backlog 023). Seluruh alur OPM **terblokir total** di produksi: membuat Analisis
  Jabatan OPM untuk jabatan apa pun ditolak dengan `409 "Sesi OPM untuk jabatan '…'
  sudah ada."` — padahal tabel `opm_sesi` **kosong** (diverifikasi: 0 baris, 2 jabatan
  berbeda, tetap 409). Pesan itu **bohong**. Dua cacat yang saling menutupi:
  - `SqlOpmSesiService.create()` menambahkan `OpmSesiModel` **tanpa `flush()`**, lalu
    menambahkan `OpmRespondenModel` (auto-responden dari SME panel) yang `sesi_id`-nya
    FK telanjang **tanpa `relationship()`** balik ke parent. Unit-of-work SQLAlchemy
    mengurutkan INSERT berdasar `relationship()` yang dikonfigurasi, bukan kolom
    `ForeignKey` mentah → INSERT `opm_responden` bisa mendahului `opm_sesi` →
    `ForeignKeyViolation`. Kini parent di-`flush()` lebih dulu (pola yang sudah dipakai
    `SqlTiSesiService.create()`), tetap lewat `_flush_checked` agar unique constraint
    `jabatan_id` tetap jadi backstop 409 untuk race dua create bersamaan.
  - `_flush_checked()` memetakan **semua** `IntegrityError` → `ConflictError("… sudah
    ada")`. `ForeignKeyViolation` adalah subclass `IntegrityError`, jadi bug di atas
    menyamar jadi konflik duplikat — menyesatkan investigasi selama dua sesi pengujian.
    Kini **hanya** `UniqueViolation` yang dipetakan ke 409; pelanggaran integritas lain
    naik apa adanya (500 + stack trace).

### Catatan pengembang

- **Kenapa bug di atas selalu lolos unit test — sebab yang sebenarnya.** Bukan karena
  `join_transaction_mode="create_savepoint"` (dugaan yang tercatat di entri `[2026-07-13]`
  dan Gotcha `CLAUDE.md`), melainkan karena **`autoflush`**: produksi memakai
  `sessionmaker(autoflush=False)` (`db.py`), sedangkan harness test memakai `Session(...)`
  dengan `autoflush=True` (default). Autoflush di test diam-diam mem-flush baris sesi saat
  `create()` menjalankan SELECT snapshot task — sehingga parent kebetulan sudah ada ketika
  anak di-INSERT, dan urutan yang salah tidak pernah terlihat. Test regresi baru
  (`test_create_sesi_tanpa_autoflush_seperti_produksi`) menjalankan `create()` di dalam
  `db_session.no_autoflush` untuk **meniru produksi**; diverifikasi gagal dengan
  `ForeignKeyViolation` bila perbaikan dicabut, dan itu satu-satunya test yang gagal —
  seluruh test OPM lain tetap hijau, membuktikan mereka buta terhadap kelas bug ini.

## [0.34.0] - 2026-07-14

### Diperbaiki

- **`__version__` tidak lagi basi.** Nilainya di-hardcode `"0.26.0"` sejak lama dan
  tidak pernah di-bump, sehingga `GET /openapi.json` (`info.version`), `/health`,
  `/ready`, dan `/version` **semuanya melaporkan versi yang salah** di produksi.
  Ini bukan sekadar kosmetik: angka itu sempat menyesatkan investigasi backlog 023
  menjadi teori "deployment lag" (dikira produksi tertinggal jauh dari `master`,
  padahal setara). Kini disamakan dengan tag rilis. **Jangan gunakan `info.version`
  sebagai bukti deploy sudah naik** kecuali disiplin bump ini dipertahankan —
  indikator yang sah adalah perilaku endpoint.

### Diubah

- **`POST /api/v1/task-inventory/sesi` kini MENOLAK (422) sesi yang panel SME-nya
  lebih besar dari `max_responden`** — sebelumnya sesi tetap dibuat (201) dan
  anggota yang berlebih **dibuang diam-diam**. Auto-populate responden dari SME
  panel memanggil `assign_ti_responden_banyak(..., max_responden=...)`, yang
  melewati anggota ke-(N+1) dengan alasan `kapasitas_penuh` — tapi
  `SqlTiSesiService.create()` **membuang `BulkAssignResult`-nya**, sehingga info
  itu tidak pernah sampai ke respons, log, maupun UI. Admin mengira seluruh panel
  terdaftar lalu menjalankan Tahap 1 → 3 → analisis, padahal sebagian ahli tidak
  pernah diundang mengisi (terjadi di produksi 2026-07-14: panel *Guru Kelas SD*
  11 anggota, `max_responden` default 10 → 1 anggota hilang tanpa jejak).
  - Pesan error **identik gaya & bentuknya dengan OPM** yang sejak awal sudah
    menolak keras kondisi yang sama: `"Jumlah anggota SME panel (11) melebihi
    max_responden (10)."` (`ValidationAppError` → 422). TI dan OPM kini konsisten.
  - Admin yang memang ingin panel besar tapi responden sedikit: naikkan
    `max_responden`, atau hapus responden setelah sesi dibuat (sudah didukung saat
    DRAFT/TAHAP1).
  - Jabatan **tanpa** panel / panel **tanpa anggota** → sesi tetap dibuat kosong
    tanpa error (perilaku eksisting, tidak berubah).
  - Tidak ada migrasi, tidak ada perubahan skema Pydantic. `openapi.json` tidak
    berubah (422 sudah terdokumentasi untuk operasi ini).

### Keamanan

- **KEBOCORAN DATA: seluruh endpoint baca kini menuntut token.** Sebelum
  perbaikan ini, **32 operasi GET** tidak memasang guard autentikasi apa pun
  (hanya `Depends(rate_limit)`) — siapa pun di internet, **tanpa token sama
  sekali**, dapat membacanya di instance produksi. Diverifikasi lewat `curl`
  langsung ke produksi, bukan sekadar pembacaan kode:
  - `GET /api/v1/partisipan` → 200 + `nama`, `email`, `authentik_user_id`
    **seluruh pegawai** (data pribadi, bocor penuh tanpa perlu menebak ID).
  - `GET /api/v1/{dcs,wcp}/hasil-responden/{id}` → 200 + hasil instrumen
    psikososial (DCS) & beban kerja/burnout (WCP) **per individu** — kategori
    data paling sensitif di aplikasi ini. Satu-satunya pelindung sebelumnya
    adalah ketidakjelasan `responden_id` (*security through obscurity*).
  - Juga `/jabatan`, `/sekolah`, `/sme-panel` (keanggotaan panel = siapa
    menilai siapa), `/jenjang-pendidikan`, `/mata-pelajaran`, `/{dcs,wcp}/hasil`
    (agregat), instrumen & katalog/master Task Inventory.
- Perbaikan: konstanta guard baru `READ_GUARDS`
  (`= [Depends(get_current_principal), Depends(rate_limit)]`, di
  `dependencies.py`) dipasang di **setiap** operasi GET. Pengecualian tunggal:
  `/health`, `/ready`, `/version` (`api/v1/system.py`) yang memang publik.
- **`POST .../search` ikut ditutup (9 endpoint).** Ini operasi *baca* yang
  mengembalikan data identik dengan `GET` pasangannya —
  `POST /api/v1/partisipan/search` membocorkan PII yang sama persis, sehingga
  menutup GET saja tidak menutup kebocorannya.
- **Guard object-level untuk hasil per individu.**
  `GET /api/v1/{dcs,wcp}/hasil-responden/{id}` kini menuntut **admin ATAU
  partisipan pemilik responden** (`authorize_responden_access`, helper yang
  sudah dipakai endpoint responden DCS/WCP/OPM/TS) — token yang sah saja tidak
  cukup: partisipan tidak boleh membaca hasil psikososial rekan kerjanya hanya
  karena dia login. Partisipan lain → **403**.
- Penjaga regresi: `tests/test_auth_guards.py` **memindai skema OpenAPI**
  (bukan daftar path tulis-tangan) dan menuntut setiap operasi baca → **401**
  tanpa token; operasi GET baru yang lupa dipasangi `READ_GUARDS` otomatis
  menggagalkan test. Ditambah test object-level (partisipan A → hasil milik B
  → 403) di `tests/test_hasil_responden_otorisasi.py`.
- Tidak ada migrasi maupun perubahan skema Pydantic — murni pemasangan guard.
  `openapi.json`: hanya penambahan `security` + respons `401`/`403`/`429`;
  bentuk request/response (skema 200) **tidak berubah**, sehingga klien
  (`anjab-abk-web-app`, `anjab-abk-mcp`) tidak perlu perubahan tipe.

## [0.33.1] - 2026-07-14

### Diperbaiki

- **`jabatan_label` DCS & WCP kini diresolusi ke nama jabatan, bukan lagi
  disalin mentah dari `jabatan_utama_id`.** Kolom "Jabatan" di tabel Daftar
  Responden `/dcs` dan `/wcp`, serta subtext header
  `/dcs/hasil-responden/{id}`/`/wcp/hasil-responden/{id}`, sebelumnya
  menampilkan ID internal (mis. `jbt_4c034eef`) alih-alih nama jabatan yang
  bisa dibaca — celah yang sengaja ditunda sejak entri `[2026-07-12]` di
  bawah.
  - `SqlDcsRespondenService`/`SqlWcpRespondenService` kini menerima
    `JabatanService` via DI (pola sama dengan `PartisipanService` yang sudah
    disuntik ke kelas yang sama), dipakai di `create_banyak()`:
    `jabatan_label = jabatan_service.get(partisipan.jabatan_utama_id).nama`.
    Fallback ke ID mentah + `logger.warning` bila jabatan tidak ditemukan
    (`NotFoundError`) — tidak menggagalkan assign.
  - `create()` (single-assign, tidak dipanggil endpoint manapun untuk
    DCS/WCP) **tidak disentuh**.
  - Skema tidak berubah — `jabatan_label` tetap kolom teks bebas
    `String(200)`, tidak ada migrasi Alembic. `openapi.json` tidak berubah
    bentuk (diverifikasi diff kosong).
  - Data existing (`dcs_responden`/`wcp_responden`) tidak dibackfill oleh
    rilis ini.

## [0.33.0] - 2026-07-14

### Diubah (BREAKING)

- **`POST /api/v1/dcs/responden` dan `POST /api/v1/wcp/responden`: response
  bulk assign berubah dari array menjadi `BulkAssignResult`.** Sebelumnya
  partisipan yang tidak memenuhi syarat (terutama "sudah terdaftar sebagai
  responden") ditolak dengan **409 untuk SELURUH batch** (atomik) — assign 10
  partisipan yang 1 di antaranya sudah terdaftar membuat 9 lainnya ikut gagal
  tanpa jejak siapa yang bermasalah. Endpoint ini disamakan dengan pola bulk
  TI/OPM/Time Study yang sudah lebih dulu benar.
  - Status code tetap **201**, tapi body respons berubah dari
    `DcsRespondenRead[]` / `WcpRespondenRead[]` menjadi
    `{"created": [...], "skipped": [{"partisipan_id": ..., "alasan": ...}]}`.
    Konsumen (`anjab-abk-web-app`, `anjab-abk-mcp`) yang mengasumsikan body
    berupa array **wajib** disesuaikan (lihat item backlog anjab-abk `019`
    untuk web app; MCP belum punya item tersendiri per rilis ini — lihat
    catatan di bawah).
  - Perilaku bulk berubah dari **atomik** menjadi **idempoten (skip-on-
    conflict)**: partisipan duplikat di payload (`duplikat_input`) atau yang
    sudah terdaftar (`sudah_terdaftar`) masuk ke `skipped` dengan alasannya;
    sisanya tetap dibuat. Batch yang **seluruhnya** di-skip tetap mengembalikan
    201 dengan `created: []` (bukan error) — nihil hasil bukan kegagalan.
  - Precondition instrumen bukan `OPEN` **tetap** 409 untuk seluruh batch
    (bukan skip per-partisipan) — tidak berubah dari perilaku sebelumnya.
  - `DcsRespondenService.create_banyak` / `WcpRespondenService.create_banyak`
    (Protocol) sekarang mengembalikan `BulkAssignResult[...]`, bukan
    `list[...]`; `InMemoryDcsRespondenService`/`InMemoryWcpRespondenService`
    tidak lagi mengimplementasikan `create_banyak` (pola yang sama dengan
    `InMemoryTsPenugasanService`/`InMemoryOpmRespondenService` — bulk assign
    butuh akses lintas-domain ke `PartisipanService` yang tidak dimiliki
    placeholder in-memory; implementasi nyata tetap di `SqlDcsRespondenService`/
    `SqlWcpRespondenService`, satu-satunya yang dipakai produksi).

## [0.32.0] - 2026-07-13

### Diperbaiki

- **Otorisasi endpoint sesi/hasil/tahap2 Task Inventory kini ditegakkan di backend**
  (sebelumnya murni kosmetik — hanya digating di frontend, backend meloloskan siapa
  pun yang bisa menjangkau API). Dua lapis guard baru:
  - **Lapis 1 — admin murni** (`Depends(require_admin)`): `GET /sesi`,
    `POST /sesi/search`, `POST /sesi` (create), `PATCH /sesi/{id}`, keempat transisi
    (`mulai-tahap1|2|3`, `tutup`), `POST /sesi/{id}/analisis`, `GET /sesi/{id}/hasil`.
    Sebelumnya sebagian besar endpoint ini **tanpa guard sama sekali** (dapat dibaca
    tanpa token), dan yang lain hanya mensyaratkan token sah tanpa cek peran — artinya
    partisipan biasa bisa menjalankan seluruh state machine sesi milik siapa pun,
    termasuk membekukan himpunan task Tahap 3 (`mulai-tahap3` — **tidak reversibel**).
  - **Lapis 2 — admin ATAU peserta sesi**, lewat helper baru `authorize_sesi_access()`
    (`dependencies.py`, sejajar `authorize_responden_access()`): `GET /sesi/{id}`,
    `GET /sesi/{id}/tahap2`, `GET /sesi/{id}/task-terpilih`. Peserta = koordinator
    sesi atau partisipan yang punya baris `TiRespondenModel` di sesi itu — mencegah
    partisipan membaca sesi jabatan lain lewat penebakan ID (BOLA/IDOR), sambil tetap
    mengizinkan alur pengisian Tahap 1/2/3 partisipan yang sah.
  - **`GET /sesi/{id}/responden`** (`taskinv_responden.py`) direlaksasi dari
    `require_admin` murni menjadi `authorize_sesi_access` (admin/peserta) —
    sebelumnya endpoint ini secara diam-diam mem-403-kan koordinator SME panel
    non-admin yang memuat halaman review Tahap 2 web app
    (`tahap2/[sesi_id]/page.tsx`), yang justru memerlukan daftar responden untuk
    menentukan apakah pengunjung adalah anggota panel.
  - `POST /sesi/{id}/tahap2` **tidak disentuh** — sudah benar (cek koordinator
    sendiri sejak awal).
  - Berlaku efektif hanya setelah perbaikan enrollment TI (entri di atas): sebelum
    itu, "punya baris responden di sesi ini" bernilai benar untuk semua partisipan
    (auto-enroll universal), sehingga guard lapis 2 tidak menyaring apa pun.
  - Tidak ada perubahan skema/model/migrasi — murni pemasangan guard.
    `openapi.json` bertambah blok `security` + respons `401`/`403` per operasi
    (bentuk request/response tidak berubah).

- **Otorisasi endpoint sesi/hasil OPM kini ditegakkan di backend** (lubang yang
  sama persis dengan Task Inventory di atas, ditemukan di audit lanjutan; OPM
  tidak punya konsep koordinator sehingga lapis 2 lebih sempit). Dua lapis guard
  baru:
  - **Lapis 1 — admin murni** (`_ADMIN_GUARDS`, pola sudah ada di
    `opm_responden.py`): `GET /opm/sesi`, `POST /opm/sesi/search`,
    `GET /opm/sesi/{id}`, `POST /opm/sesi` (create), `PATCH /opm/sesi/{id}`,
    `POST /sesi/{id}/buka`, `POST /sesi/{id}/tutup`, `POST /sesi/{id}/analisis`,
    `GET /sesi/{id}/hasil`. Sebagian tanpa guard sama sekali, sebagian lain
    hanya token sah tanpa cek peran — partisipan biasa bisa membuka/menutup
    sesi OPM milik siapa pun dan menjalankan analisisnya.
  - **Lapis 2 — admin ATAU responden sesi ini**, lewat helper baru
    `authorize_opm_sesi_access()` (`dependencies.py`) — **hanya**
    `GET /sesi/{id}/task`, satu-satunya endpoint sesi-level yang dipanggil
    halaman pengisian partisipan (`opm/isi/[responden_id]`). Peserta = partisipan
    yang punya baris `OpmRespondenModel` di sesi itu (tanpa cabang koordinator —
    `OpmSesiModel` tidak punya kolom itu).
  - Endpoint responden OPM (`opm_responden.py`) dan `GET /opm/kuesioner/saya`
    **tidak disentuh** — sudah benar sejak awal (assignment-based, tidak ada
    auto-enroll universal seperti bug TI di atas).
  - Tidak ada perubahan skema/model/migrasi — murni pemasangan guard.
    `openapi.json` bertambah blok `security` + respons `401`/`403` per operasi
    (bentuk request/response tidak berubah).

- **`GET /task-inventory/kuesioner/saya` kini murni pembacaan — tidak lagi
  mendaftarkan partisipan sebagai responden ke SEMUA sesi Task Inventory
  aktif.** Bug lama: endpoint ini mencari seluruh sesi TAHAP1/TAHAP2/TAHAP3
  tanpa filter partisipan, lalu memanggil `ensure_for_partisipan()` yang
  meng-INSERT baris `TiRespondenModel` untuk tiap sesi — membuat partisipan
  bisa "terdaftar" ke sesi jabatan yang bukan urusannya, dan membatalkan
  penyaringan SME panel yang sudah berjalan di jalur enrollment `create()`
  sesi (item `0.31.0`). Endpoint sekarang memakai `list_by_partisipan()`,
  pola yang sama dengan OPM — hanya menampilkan sesi tempat partisipan
  memang sudah terdaftar sebagai responden.
  - `ensure_for_partisipan()` **dihapus total** dari `TiRespondenService`
    (Protocol, impl in-memory, impl SQL) — tidak ada pemanggil lain.
  - Kontrak `TiKuesionerItemRead` **tidak berubah**; `openapi.json` tidak
    berubah bentuk skema (hanya deskripsi endpoint).
  - **Tidak membersihkan data lama** — partisipan yang sudah terlanjur
    ter-enroll ke sesi yang bukan haknya (lewat bug ini) tetap punya baris
    `ti_responden` sampai dibersihkan lewat langkah terpisah (butuh
    konfirmasi eksplisit, di luar lingkup perbaikan ini).
  - Koreksi dokumentasi: revisi `[2026-06-21]` di `CLAUDE.md` sempat
    menyatakan Task Inventory "tetap menggunakan flow yang sama (assignment
    manual via tambah-responden)" — klaim itu **tidak pernah benar di kode**;
    ditandai sebagai keliru di `CLAUDE.md`.

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
