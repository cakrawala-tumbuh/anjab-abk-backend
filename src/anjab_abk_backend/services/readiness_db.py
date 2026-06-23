"""Implementasi `ReadinessCheck` untuk PostgreSQL.

Mengisi seam readiness backend-skill: `/api/v1/ready` akan `503` bila DB tak dapat
dijangkau. `check()` async (kontrak Protocol), tetapi ping DB bersifat blocking,
jadi dijalankan di threadpool via `anyio.to_thread` agar tidak memblok event loop.
"""

from __future__ import annotations

import logging

import anyio

from ..db import ping

logger = logging.getLogger("app.db")


class DatabaseReadinessCheck:
    """Cek kesiapan: koneksi PostgreSQL hidup (`SELECT 1`)."""

    name = "postgresql"

    async def check(self) -> bool:
        try:
            await anyio.to_thread.run_sync(ping)
            return True
        except Exception:  # noqa: BLE001 — readiness tidak boleh melempar; cukup laporkan gagal
            logger.warning("readiness postgresql gagal", exc_info=True)
            return False
