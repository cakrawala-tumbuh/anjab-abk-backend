# anjab-abk-backend

Backend REST API untuk **ANJAB** (Analisis Jabatan) dan **ABK** (Analisis Beban Kerja)
yayasan pendidikan, dibangun dengan **FastAPI**.

## Menjalankan (development)

```bash
pip install -e .
uvicorn anjab_abk_backend.main:create_app --factory --reload
# atau (prod-like):
python -m anjab_abk_backend
```

- Swagger UI  → http://localhost:8000/docs
- ReDoc       → http://localhost:8000/redoc
- Health      → http://localhost:8000/api/v1/health

## Deploy (Docker)

Inisialisasi database **otomatis** — tidak ada langkah manual. Entrypoint container
menjalankan migrasi + seed master data sebelum aplikasi naik:

```bash
docker run -d \
  -e DATABASE_URL="postgresql+psycopg://user:pass@host:5432/dbname" \
  -e AUTHENTIK_ISSUER="https://auth.example.com/" \
  -p 8000:8000 ghcr.io/<owner>/anjab-abk-backend:latest
```

Saat start, entrypoint menjalankan `python -m anjab_abk_backend.initdb`:
`alembic upgrade head` lalu seed master data. **Aman diulang tiap `up -d`/restart** —
tabel `alembic_version` mencegah migrasi lama dijalankan ulang dan seed melompati baris
yang sudah ada (start kedua dst. praktis no-op). Cocok untuk deployment **satu instance**;
untuk multi-replica, jalankan `initdb` sebagai job init terpisah (sekali, sebelum app).

> Migrasi manual (mis. dari checkout source) tetap bisa: `alembic upgrade head`.
> Cara membuat revisi saat model berubah: lihat `CLAUDE.md` → "Migrasi Database".

## Test

```bash
make test   # lint + unit di Docker (gate — dari skill automated-test)
```

## Konfigurasi

Lihat `.env.example`. Semua via environment (12-factor).

### Feature flag

Lima fungsi dapat dimatikan independen lewat env, semuanya default `false` (fail-closed):
`FEATURE_AI_NARRATIVE_DRAFT`, `FEATURE_PARTICIPANT_VALIDATION`, `FEATURE_WCP_DCS_SCORING`,
`FEATURE_RESEARCH_EXPORT`, `FEATURE_CHANGE_AUTHORIZATION`. Perubahan butuh restart. Status
dapat dibaca (bertoken) lewat `GET /api/v1/system/fitur`.

### Menyalakan AI

AI menyala hanya bila semua syarat ini terpenuhi; memilih penyedia tidak dengan sendirinya
menyalakan AI:

1. Flag `FEATURE_AI_NARRATIVE_DRAFT=true` (env, butuh restart) dan saklar layanan AI hidup.
2. `AI_JENIS_SUMBER_DIIZINKAN` (env) mengizinkan jenis sumber yang dipakai; bawaan hanya
   `["SINTETIS"]`. Gerbang data (jenis sumber, PII, flag, saklar) sama untuk semua penyedia.
3. `AI_FUNGSI_AKTIF` (env) mendaftarkan fungsi AI yang boleh dipakai.
4. Penyedia siap lewat UI admin (disimpan di basis data, berlaku pada job berikutnya tanpa
   restart): `API_ANTHROPIC` dengan kunci API terpasang, atau `LANGGANAN_CLAUDE` dengan CLI
   yang sudah masuk (paket langganan Anthropic, bukan Anthropic API; lihat catatan risiko di bawah).
   Mode `MATI` (bawaan) membuat pengajuan ditolak dan job antre selesai manual
   `PENYEDIA_MATI`. `AI_KREDENSIAL_KUNCI_INDUK` (env) wajib untuk menyimpan kunci API.
5. Keputusan tertulis K-8 untuk membuka jenis sumber di luar `SINTETIS`.

Env `ANTHROPIC_API_KEY`, `AI_MODEL`, dan `AI_EFFORT` tidak lagi dibaca; model, effort, dan
kunci hanya berasal dari pengaturan penyedia. Tiap `ai_run` mencatat `penyedia`.

### Penyedia `LANGGANAN_CLAUDE` (catatan risiko)

Mode ini memanggil model lewat binary Claude Code (`claude -p`) yang terpasang di image,
bukan lewat Anthropic API. Aplikasi tidak menerima, menyimpan, membaca, atau mengantarai
kredensial langganan: tidak ada kolom, env, endpoint, atau formulir untuknya. Pemakaian
mode ini adalah tanggung jawab pemilik akun yang masuk, dan **README ini tidak menyatakan
bahwa pemakaian ini diizinkan Anthropic**. Pertanyaan izin diarahkan dokumen Anthropic ke
tim sales mereka.

Yang tertulis di dokumen Anthropic (dibaca 5 November 2026; periksa ulang sebelum memakai):

- <https://code.claude.com/docs/en/legal-and-compliance.md>: pengembang produk "should use
  API key authentication"; Anthropic "does not permit third-party developers to offer
  Claude.ai login into their own applications, or to route requests through Free, Pro, Max,
  or Ultra plan credentials on behalf of their users"; pengembang "may not collect, store,
  or intermediate Claude.ai credentials or session tokens"; memasang atau menjalankan
  Claude Code di produk atau layanan "requires agreeing to our Commercial Terms of
  Service" dengan binary yang tidak diubah. Batas pemakaian paket "assume ordinary,
  individual usage", dan Anthropic "reserves the right to take measures to enforce these
  restrictions and may do so without prior notice".
- <https://code.claude.com/docs/en/data-usage.md>: untuk paket konsumen, data dipakai
  melatih model "when this setting is on" (retensi 5 tahun bila aktif, 30 hari bila tidak);
  pengaturannya ada di <https://claude.ai/settings/data-privacy-controls>.

Akibat teknis: pemakaian dihitung terhadap batas paket langganan (bukan tagihan API), retensi
dan pelatihan mengikuti pengaturan akun yang masuk, dan `inference_geo`, ZDR, serta batas
biaya workspace **tidak berlaku** pada mode ini. Hanya grup `admin` yang dapat memilih mode,
dan menyalakan AI tetap mengikuti K-8.

Cara masuk (dilakukan operator, di dalam kontainer, lewat alur Anthropic sendiri):

```bash
docker compose exec -u appuser <layanan> claude auth login
```

Sesi tersimpan di `CLAUDE_CONFIG_DIR=/var/lib/claude-config` (diset di image, milik
`appuser`); agar bertahan antar-restart, pasang volume di path itu pada deployment.
`claude` dipin ke versi `CLAUDE_CODE_VERSION` di `Dockerfile` (repo apt bertanda tangan,
sidik jari kunci diperiksa saat build). Model baru dapat menuntut versi yang lebih baru;
model yang ditolak binary berakhir sebagai `MODEL_PERMANEN` dan perbaikannya menaikkan ARG
itu. Mode ini gagal-tertutup tanpa percobaan ulang: `PENYEDIA_TIDAK_TERSEDIA` bila binary
tidak ada dan `LANGGANAN_BELUM_MASUK` bila CLI belum masuk.

Dampak ukuran image: binary menambah sekitar 280 MiB terpasang (paket 134 MB terkompresi)
pada target `runtime`, sehingga image kira-kira 2,3 kali lebih besar bagi semua pemakai,
juga yang tidak pernah memilih mode ini.

### Evaluasi perilaku model (`make eval-ai`)

Harness `evals/` menjalankan kasus **sintetis** fungsi AI lewat jalur yang dipilih operator
dan menghasilkan vonis ber-exit-code. Ia berjalan **di luar** `make test` (yang tanpa jaringan
dan tanpa kredensial) dan di luar CI: `.github/workflows/` tidak memanggilnya. Tanpa basis
data, tanpa `AiGateway`, tanpa menyalakan flag. Kredensial tidak pernah masuk repo, `Settings`,
`.env`, argumen perintah, secret GitHub, log, maupun laporan.

**Menutup issue harness BUKAN bukti perilaku model.** Hasil hanya berlaku untuk jalur dan model
yang tercantum di baris `#EVAL`, bukan untuk jalur atau model lain yang kelak dipilih admin.
Evaluasi nyata dijalankan operator setelah kredensial tersedia.

```bash
# Jalur API: kunci workspace evaluasi di env proses (terpisah dari kunci produksi).
# Diteruskan sebagai `docker run -e ANTHROPIC_API_KEY` tanpa nilai. Tujuan inferensi geo `us`
# dan fallback penolakan mati dipasang oleh target ini.
ANTHROPIC_API_KEY=... make eval-ai FUNGSI=P10 PENYEDIA=API_ANTHROPIC

# Jalur langganan: volume Docker BERNAMA berisi sesi masuk CLI (path host ditolak).
make eval-ai FUNGSI=P10 PENYEDIA=LANGGANAN_CLAUDE CLAUDE_VOLUME=eval-claude
```

`FUNGSI` menerima `P10` (draf narasi) dan `P09` (kritik AI atas versi narasi; 12 kasus di
`evals/p09/kasus.json`, dinilai atas kategori temuan, draf bersih, dan span, bukan atas
`draft_text`). `P01` (ekstraksi fakta dari dokumen sumber; 10 kasus di `evals/p01/kasus.json`, dinilai atas
sifat fakta, angka baru, pola klaim terlaksana, dan span fakta, bukan atas `draft_text`). Fungsi baru wajib lulus evaluasi ini sebelum operator memasukkannya ke
`AI_FUNGSI_AKTIF`.

`PENYEDIA` wajib dan tanpa nilai bawaan; kosong atau tak dikenal ditolak sebelum build dan
sebelum `docker run`. `CLAUDE_VOLUME` wajib untuk jalur langganan dan harus berupa nama volume
(`^[A-Za-z0-9][A-Za-z0-9_.-]*$`). Opsional: `EVAL_ULANG` (bawaan 3; kasus lulus hanya bila
semua ulangan lulus) dan `EVAL_MAKS_TOKEN` (bawaan 500000, dihitung dari token masukan +
keluaran). Model dan effort dari konstanta bawaan (`ai/penyedia.py`), bukan env.

Masuk untuk jalur langganan (sekali, oleh operator; alur Anthropic sendiri di dalam kontainer):

```bash
docker volume create eval-claude
docker run --rm -it -v eval-claude:/var/lib/claude-config --entrypoint claude \
  <image-eval> auth login      # image-eval: <nama-direktori-repo>-eval, hasil `make eval-ai`
```

`make` mengubah semua kegagalan resep menjadi exit 2, jadi **kode harness dibaca dari baris
akhir `#EVAL`** yang selalu tercetak (juga pada exit 2 dan galat tak terduga). Laporan hanya
ke stdout: satu baris JSON per ulangan, lalu `#EVAL penyedia=... model=... kode=... exit=...`.

| exit | Arti |
|---|---|
| 0 | semua kasus lulus |
| 1 | gagal perilaku (`GAGAL_PERILAKU`) |
| 2 | argumen atau kasus rusak, atau galat tak terduga |
| 3 | kunci API tak ada (`KUNCI_TIDAK_ADA`) |
| 4 | tak konklusif: galat sementara berulang atau batas token (`TAK_KONKLUSIF`, `BATAS_TOKEN`); tidak dihitung gagal perilaku |
| 5 | gagal permanen: `SKEMA_DITOLAK_API` (jalur API) atau `CLI_GAGAL_PERMANEN` (langganan); evaluasi berhenti |
| 6 | langganan belum masuk (`LANGGANAN_BELUM_MASUK`), nol panggilan model |
| 7 | binary `claude` tak ada (`BINARY_CLAUDE_TIDAK_ADA`), nol panggilan model |

Kasus ada di `evals/<kode>/kasus.json` (satu berkas per fungsi). Seluruhnya sintetis dengan
nama fiktif; `jenis` sumber selain `SINTETIS` ditolak (exit 2), kecuali kasus tanpa model yang
justru menguji penolakan jenis berawalan `WCP`/`DCS`/`KONSELING`/`MURID`. Penilai
deterministik (tanpa model penilai). Bagian manusia R11-016 (blind reviewer) tidak
digantikan harness.
