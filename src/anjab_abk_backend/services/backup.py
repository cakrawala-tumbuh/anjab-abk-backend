"""Layanan backup & restore basis data PostgreSQL lewat `pg_dump`/`pg_restore` (backlog 025).

Sebelum modul ini ada, cadangan basis data hanya bisa diambil lewat `scripts/backup.sh`/
`scripts/restore.sh` — menuntut akses shell ke host produksi yang tidak dimiliki admin
yayasan. `BackupService` menjalankan `pg_dump`/`pg_restore` sebagai **subprocess** memakai
`DatabaseSettings` yang sama dipakai `db.py`, sehingga tidak ada konfigurasi koneksi baru
dan tidak ada duplikasi logika penguraian `DATABASE_URL`.

Kredensial TIDAK PERNAH muncul sebagai argumen command line (bisa terbaca lewat `ps aux`
oleh user lain di host yang sama) — sandi dioper lewat environment `PGPASSWORD`; komponen
lain (`-h`/`-p`/`-U`/`-d`) sebagai argumen terpisah, meniru pola `scripts/backup.sh`.

Server TIDAK menyimpan salinan cadangan: `stream_dump()` mengalirkan langsung keluaran
`pg_dump` ke pemanggil tanpa menulis salinan permanen di disk (hanya berkas sementara
sekali-pakai untuk unggahan restore, dihapus otomatis begitu blok `with` selesai).
"""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime
from tempfile import NamedTemporaryFile
from typing import IO

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ProgrammingError

from ..db import DatabaseSettings, dispose_engine, get_engine
from ..errors import ValidationAppError
from ..migrate import current_heads
from ..schemas.backup import RestoreResult

logger = logging.getLogger("anjab_abk_backend.services.backup")

_CHUNK_SIZE = 65_536


class BackupService:
    """Backup & restore basis data PENUH lewat `pg_dump`/`pg_restore` (subprocess).

    Bukan seam dengan implementasi alternatif (tidak ada varian in-memory yang masuk
    akal untuk operasi ini) — mengikuti pola `db.py` yang juga langsung terikat ke
    PostgreSQL nyata.
    """

    def __init__(self, db_settings: DatabaseSettings) -> None:
        self._db_settings = db_settings

    def _connection_params(self) -> tuple[str, int, str, str, str]:
        """Uraikan `DATABASE_URL`/komponen `DB_*` jadi tuple argumen `pg_dump`/`pg_restore`.

        Berlaku sama untuk DSN lengkap (`DATABASE_URL=postgresql+psycopg://...`) maupun
        komponen terpisah (`DB_HOST`, dst) — keduanya melewati `sqlalchemy_url()` lebih
        dulu sehingga logika penguraian ini seragam. Prefiks driver SQLAlchemy
        (`postgresql+psycopg://`) ditanggalkan karena `pg_dump`/`pg_restore` adalah
        biner `libpq`, bukan driver Python — meniru `scripts/backup.sh`.
        """
        raw = self._db_settings.sqlalchemy_url()
        url = raw if isinstance(raw, URL) else make_url(raw)
        host = url.host or "127.0.0.1"
        port = url.port or 5432
        user = url.username or "postgres"
        password = url.password or ""
        database = url.database or ""
        return host, port, user, password, database

    @property
    def database_name(self) -> str:
        """Nama basis data tujuan — dipakai memvalidasi field `konfirmasi` pada restore."""
        return self._connection_params()[4]

    def backup_filename(self) -> str:
        """Nama berkas unduhan bertimestamp, mis. `anjab-abk-backup_20260726_143000.dump`."""
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        return f"anjab-abk-backup_{ts}.dump"

    def stream_dump(self) -> Iterator[bytes]:
        """Jalankan `pg_dump --format=custom --no-acl --no-owner` dan alirkan stdout-nya.

        Kembalian berupa generator byte per potongan 64 KiB — dipakai sebagai body
        `StreamingResponse` sehingga server tidak pernah menahan dump penuh di memori
        atau disk. Batasan inheren streaming: `StreamingResponse` mengirim header HTTP
        (status 200) SEBELUM potongan pertama diminta dari generator ini — bila `pg_dump`
        gagal setelah sebagian byte terlanjur terkirim, kegagalan itu hanya bisa dicatat
        ke log (`pg_dump_gagal`), tidak lagi bisa diubah jadi status HTTP lain.
        """
        host, port, user, password, dbname = self._connection_params()
        env = {**os.environ, "PGPASSWORD": password}
        cmd = [
            "pg_dump",
            "-h",
            host,
            "-p",
            str(port),
            "-U",
            user,
            "-d",
            dbname,
            "--format=custom",
            "--no-acl",
            "--no-owner",
        ]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        assert proc.stdout is not None  # noqa: S101 — dijamin oleh stdout=PIPE di atas
        try:
            while True:
                chunk = proc.stdout.read(_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        finally:
            proc.stdout.close()
            returncode = proc.wait()
            if returncode != 0:
                stderr = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
                logger.error(
                    "pg_dump_gagal",
                    extra={"returncode": returncode, "stderr": stderr[-2000:]},
                )

    def restore(self, berkas: IO[bytes], konfirmasi: str) -> RestoreResult:
        """Restore basis data penuh dari dump `pg_dump --format=custom`.

        Menolak (`ValidationAppError` → 422, basis data TIDAK tersentuh) bila
        `konfirmasi` tidak persis sama dengan nama basis data tujuan. Menutup pool
        koneksi aplikasi (`dispose_engine()`) sebelum DAN sesudah `pg_restore --clean`
        dijalankan — `--clean` men-drop objek yang mungkin masih dipegang koneksi
        aktif SQLAlchemy, dan koneksi baru perlu dibuka ulang setelah objeknya
        dipulihkan. Skema TIDAK di-upgrade otomatis: revisi `alembic_version` hasil
        restore hanya DIBACA & dibandingkan dengan head aplikasi; bila berbeda,
        dikembalikan sebagai `peringatan` (bukan dieksekusi).

        Args:
            berkas: stream biner berkas dump yang diunggah (`UploadFile.file`).
            konfirmasi: nama basis data yang diketik admin untuk konfirmasi.

        Returns:
            `RestoreResult` dengan revisi Alembic hasil restore dan peringatan bila ada.

        Raises:
            ValidationAppError: `konfirmasi` tidak cocok, atau `pg_restore` gagal
                (mis. berkas bukan dump `pg_dump --format=custom` yang valid).
        """
        db_name = self.database_name
        if konfirmasi != db_name:
            raise ValidationAppError(
                f"Konfirmasi tidak cocok. Ketik persis nama basis data '{db_name}' untuk"
                " melanjutkan restore."
            )

        with NamedTemporaryFile(suffix=".dump") as tmp:
            _copy_to_temp(berkas, tmp)
            tmp.flush()
            dispose_engine()
            try:
                self._run_pg_restore(tmp.name)
            finally:
                dispose_engine()

        revisi = self._read_alembic_version()
        peringatan: list[str] = []
        heads = current_heads()
        head = heads[0] if len(heads) == 1 else None
        if revisi != head:
            peringatan.append(
                f"Revisi skema hasil restore ('{revisi}') berbeda dari head aplikasi"
                f" ('{head}'). Jalankan migrasi (`alembic upgrade head`) secara manual"
                " sebelum melanjutkan operasional — endpoint ini TIDAK meng-upgrade"
                " skema secara otomatis."
            )
        return RestoreResult(status="ok", revisi_alembic=revisi, peringatan=peringatan)

    def _run_pg_restore(self, dump_path: str) -> None:
        host, port, user, password, dbname = self._connection_params()
        env = {**os.environ, "PGPASSWORD": password}
        cmd = [
            "pg_restore",
            "-h",
            host,
            "-p",
            str(port),
            "-U",
            user,
            "-d",
            dbname,
            "--clean",
            "--if-exists",
            "--no-acl",
            "--no-owner",
            "--single-transaction",
            dump_path,
        ]
        result = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error(
                "pg_restore_gagal",
                extra={"returncode": result.returncode, "stderr": result.stderr[-4000:]},
            )
            raise ValidationAppError(
                "Restore gagal: berkas bukan dump `pg_dump --format=custom` yang valid,"
                " atau tidak kompatibel dengan basis data tujuan. Basis data tidak diubah"
                " (--single-transaction membatalkan seluruh perubahan bila gagal di tengah)."
            )

    def _read_alembic_version(self) -> str | None:
        """Baca `alembic_version.version_num` langsung dari basis data hasil restore."""
        with get_engine().connect() as conn:
            try:
                row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
            except ProgrammingError:
                return None
            return row[0] if row else None


def _copy_to_temp(src: IO[bytes], dst: IO[bytes]) -> None:
    """Salin `src` ke `dst` per potongan (hindari memuat seluruh berkas ke memori)."""
    while True:
        chunk = src.read(_CHUNK_SIZE)
        if not chunk:
            break
        dst.write(chunk)
