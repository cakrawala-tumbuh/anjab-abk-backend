"""Implementasi `RisetProtokolService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from psycopg.errors import UniqueViolation
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..errors import ConflictError, NotFoundError
from ..models import RisetProtokolModel
from ..schemas.riset_protokol import (
    RisetProtokolCreate,
    RisetProtokolRead,
    RisetProtokolRingkas,
    StatusProtokol,
)
from .riset_protokol import ProtokolTerkunciError
from .riset_signoff_sql import signoff_ada


def hash_isi(isi: str) -> str:
    """Hitung SHA-256 heksadesimal atas UTF-8 `isi` persis seperti tersimpan.

    Args:
        isi: Isi protokol.

    Returns:
        String heksadesimal 64 karakter.
    """
    return hashlib.sha256(isi.encode("utf-8")).hexdigest()


def _aware(dt: datetime | None) -> datetime | None:
    """Pastikan datetime ber-zona waktu (UTC) sebelum masuk skema respons."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _ringkas(rec: RisetProtokolModel) -> RisetProtokolRingkas:
    """Petakan baris ORM ke ringkasan tanpa `isi`."""
    return RisetProtokolRingkas(
        id=rec.id,
        kode=rec.kode,
        versi=rec.versi,
        judul=rec.judul,
        status=StatusProtokol(rec.status),
        isi_hash=rec.isi_hash,
        dibuat_oleh=rec.dibuat_oleh,
        dikunci_oleh=rec.dikunci_oleh,
        dikunci_pada=_aware(rec.dikunci_pada),
        created_at=_aware(rec.created_at),  # type: ignore[arg-type]
        updated_at=_aware(rec.updated_at),  # type: ignore[arg-type]
    )


def _to_read(rec: RisetProtokolModel, *, signoff_ada: bool = False) -> RisetProtokolRead:
    """Petakan baris ORM ke representasi lengkap (dengan `isi` dan `signoff_ada`)."""
    return RisetProtokolRead(**_ringkas(rec).model_dump(), isi=rec.isi, signoff_ada=signoff_ada)


class SqlRisetProtokolService:
    """`RisetProtokolService` berbasis PostgreSQL; terikat satu `Session` per request.

    Baris tidak pernah dihapus; satu-satunya perubahan adalah `kunci()` sekali jalan.
    """

    def __init__(self, session: Session) -> None:
        """Simpan sesi per-request yang dipakai seluruh operasi."""
        self._s = session

    def create(self, data: RisetProtokolCreate, *, dibuat_oleh: str) -> RisetProtokolRead:
        """Simpan protokol `DRAF` baru dengan `versi` = versi terbesar `kode` + 1.

        Flush berjalan dalam SAVEPOINT; hanya `UniqueViolation` (dua permintaan bersamaan
        mendapat versi yang sama) dipetakan ke 409, pelanggaran lain naik apa adanya.

        Raises:
            ConflictError: Pasangan (`kode`, `versi`) bentrok (409).
        """
        m = RisetProtokolModel
        terbesar = self._s.scalar(select(func.max(m.versi)).where(m.kode == data.kode)) or 0
        now = datetime.now(UTC)
        rec = RisetProtokolModel(
            id=str(uuid.uuid4()),
            kode=data.kode,
            versi=terbesar + 1,
            judul=data.judul,
            isi=data.isi,
            status=StatusProtokol.DRAF.value,
            dibuat_oleh=dibuat_oleh,
            created_at=now,
            updated_at=now,
        )
        try:
            with self._s.begin_nested():
                self._s.add(rec)
                self._s.flush()
        except IntegrityError as exc:
            if isinstance(exc.orig, UniqueViolation):
                raise ConflictError(
                    f"Versi {rec.versi} protokol '{data.kode}' baru saja dibuat; ulangi permintaan."
                ) from exc
            raise
        self._s.refresh(rec)
        return _to_read(rec)

    def get(self, protokol_id: str) -> RisetProtokolRead:
        """Ambil satu protokol; `NotFoundError` (404) bila tak ada."""
        rec = self._s.get(RisetProtokolModel, protokol_id)
        if rec is None:
            raise NotFoundError(f"Protokol riset '{protokol_id}' tidak ditemukan.")
        return _to_read(rec, signoff_ada=signoff_ada(self._s, rec.id))

    def list(
        self, *, kode: str | None, status: str | None, limit: int, offset: int
    ) -> tuple[list[RisetProtokolRingkas], int]:
        """Daftar ringkas terbaru dulu; filter `kode`/`status` opsional."""
        m = RisetProtokolModel
        conds = []
        if kode is not None:
            conds.append(m.kode == kode)
        if status is not None:
            conds.append(m.status == status)
        total = self._s.scalar(select(func.count()).select_from(m).where(*conds)) or 0
        rows = self._s.scalars(
            select(m).where(*conds).order_by(m.created_at.desc(), m.id).limit(limit).offset(offset)
        ).all()
        return [_ringkas(r) for r in rows], total

    def kunci(self, protokol_id: str, *, dikunci_oleh: str) -> RisetProtokolRead:
        """Kunci protokol: baris dikunci `FOR UPDATE` agar dua kunci bersamaan tak lolos.

        Raises:
            NotFoundError: Protokol tak ada (404).
            ProtokolTerkunciError: Sudah `TERKUNCI` (409 `PROTOKOL_TERKUNCI`).
        """
        rec = self._s.get(RisetProtokolModel, protokol_id, with_for_update=True)
        if rec is None:
            raise NotFoundError(f"Protokol riset '{protokol_id}' tidak ditemukan.")
        if rec.status == StatusProtokol.TERKUNCI.value:
            raise ProtokolTerkunciError(
                f"Protokol riset '{rec.kode}' versi {rec.versi} sudah terkunci."
            )
        now = datetime.now(UTC)
        rec.status = StatusProtokol.TERKUNCI.value
        rec.isi_hash = hash_isi(rec.isi)
        rec.dikunci_oleh = dikunci_oleh
        rec.dikunci_pada = now
        rec.updated_at = now
        self._s.flush()
        self._s.refresh(rec)
        return _to_read(rec, signoff_ada=signoff_ada(self._s, rec.id))
