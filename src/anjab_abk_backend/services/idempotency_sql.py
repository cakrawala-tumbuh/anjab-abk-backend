"""Implementasi `IdempotencyStore` di atas PostgreSQL.

Merealisasikan catatan di seam backend-skill ("INSERT ... ON CONFLICT"): di
PostgreSQL hal ini benar-benar memakai **`INSERT ... ON CONFLICT DO NOTHING
RETURNING`** — lebih bersih dari pola "catch IntegrityError" karena tidak
membatalkan transaksi saat duplikat.

Semantik transaksi (penting):
- `reserve()` melakukan `INSERT ... ON CONFLICT (key) DO NOTHING RETURNING key`.
  Bila baris baru tersisip → mengembalikan key → `True`. Bila key sudah ada → tidak
  ada baris dikembalikan → `False`. Tidak perlu SAVEPOINT: `DO NOTHING` bukan error,
  jadi transaksi request tetap sehat. Untuk request paralel dengan key sama, INSERT
  kedua **menunggu** sampai yang pertama commit/rollback, lalu: bila pertama commit →
  konflik → `False`; bila rollback → tersisip → `True`. Inilah mutual exclusion yang
  dijanjikan kontrak `reserve`.
- Semua operasi (reserve → create → save) berbagi SATU sesi/transaksi per request
  (lihat db.get_session), sehingga reservasi + hasil commit atomik di akhir request.
- TTL (`expires_at`) dibandingkan **server-side** (`func.now()`, timestamptz) — bebas
  dari masalah aware/naive. Pembersihan baris kedaluwarsa = job terjadwal di luar skill.
- Key efektif (sudah di-scope `{method}:{path}:{key}` oleh lapisan dependency) di-**hash**
  (SHA-256) sebelum jadi primary key. Ini membatasi panjang ke 64 char (cegah error saat
  klien mengirim Idempotency-Key panjang) tanpa mengubah kontrak — store tetap menerima
  `key: str` apa adanya.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ..db import get_db_settings
from ..models import IdempotencyRecord


def _utcnow() -> datetime:
    """UTC aware (kolom memakai timestamptz)."""
    return datetime.now(UTC)


def _digest(key: str) -> str:
    """Hash key efektif → 64 char hex (batasi panjang & normalisasi penyimpanan)."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


class SqlIdempotencyStore:
    """`IdempotencyStore` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get(self, key: str) -> dict[str, Any] | None:
        """Kembalikan hasil tersimpan untuk replay (hanya bila completed & belum kedaluwarsa)."""
        rec = self._s.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.key == _digest(key),
                IdempotencyRecord.completed.is_(True),
                or_(
                    IdempotencyRecord.expires_at.is_(None),
                    IdempotencyRecord.expires_at > func.now(),
                ),
            )
        )
        return rec.response if rec is not None else None

    def reserve(self, key: str) -> bool:
        """Tandai key 'sedang diproses' secara atomik (`INSERT ... ON CONFLICT DO NOTHING`)."""
        ttl = get_db_settings().db_idempotency_ttl_seconds
        expires = _utcnow() + timedelta(seconds=ttl) if ttl > 0 else None
        stmt = (
            pg_insert(IdempotencyRecord)
            .values(key=_digest(key), completed=False, expires_at=expires)
            .on_conflict_do_nothing(index_elements=["key"])
            .returning(IdempotencyRecord.key)
        )
        inserted = self._s.scalar(stmt)
        return inserted is not None

    def save(self, key: str, value: dict[str, Any]) -> None:
        """Simpan hasil final → tandai completed (UPDATE baris reservasi)."""
        rec = self._s.get(IdempotencyRecord, _digest(key))
        if rec is None:  # jalur defensif bila reserve dilewati
            rec = IdempotencyRecord(key=_digest(key))
            self._s.add(rec)
        rec.response = value
        rec.completed = True
        self._s.flush()

    def release(self, key: str) -> None:
        """Lepas reservasi (operasi gagal) agar key bisa di-retry."""
        rec = self._s.get(IdempotencyRecord, _digest(key))
        if rec is not None:
            self._s.delete(rec)
            self._s.flush()
