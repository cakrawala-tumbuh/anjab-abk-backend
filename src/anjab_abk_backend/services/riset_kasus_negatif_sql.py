"""Implementasi `RisetKasusNegatifService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..errors import NotFoundError
from ..models import RisetKasusNegatifModel, RisetProtokolModel
from ..schemas.riset_kasus_negatif import RisetKasusNegatifCreate, RisetKasusNegatifRead
from ..schemas.riset_protokol import StatusProtokol
from .riset_statistik import ProtokolBelumTerkunciError


def _aware(dt: datetime) -> datetime:
    """Pastikan datetime ber-zona waktu (UTC) sebelum masuk skema respons."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_read(rec: RisetKasusNegatifModel) -> RisetKasusNegatifRead:
    """Petakan baris ORM ke representasi respons."""
    return RisetKasusNegatifRead(
        id=rec.id,
        protokol_id=rec.protokol_id,
        ringkasan=rec.ringkasan,
        alasan_negatif=rec.alasan_negatif,
        sumber_ref=rec.sumber_ref,
        dibuat_oleh=rec.dibuat_oleh,
        created_at=_aware(rec.created_at),
    )


class SqlRisetKasusNegatifService:
    """`RisetKasusNegatifService` berbasis PostgreSQL; terikat satu `Session` per request.

    Baris tidak pernah diubah maupun dihapus.
    """

    def __init__(self, session: Session) -> None:
        """Simpan sesi per-request yang dipakai seluruh operasi."""
        self._s = session

    def _protokol(self, protokol_id: str, *, for_share: bool = False) -> RisetProtokolModel:
        """Ambil protokol atau lempar `NotFoundError` (404).

        Args:
            protokol_id: ID protokol riset.
            for_share: Bila benar, baris dikunci `FOR SHARE` agar status protokol tidak
                berubah selama transaksi pencatatan kasus negatif.
        """
        stmt = select(RisetProtokolModel).where(RisetProtokolModel.id == protokol_id)
        if for_share:
            stmt = stmt.with_for_update(read=True)
        rec = self._s.scalar(stmt)
        if rec is None:
            raise NotFoundError(f"Protokol riset '{protokol_id}' tidak ditemukan.")
        return rec

    def create(
        self, protokol_id: str, data: RisetKasusNegatifCreate, *, dibuat_oleh: str
    ) -> RisetKasusNegatifRead:
        """Simpan kasus negatif; protokol harus `TERKUNCI`.

        Raises:
            NotFoundError: Protokol tak ada (404).
            ProtokolBelumTerkunciError: Protokol masih `DRAF` (409 `PROTOKOL_BELUM_TERKUNCI`).
        """
        protokol = self._protokol(protokol_id, for_share=True)
        if protokol.status != StatusProtokol.TERKUNCI.value:
            raise ProtokolBelumTerkunciError(
                f"Protokol riset '{protokol.kode}' versi {protokol.versi} belum terkunci; "
                "kasus negatif hanya dapat dicatat untuk protokol TERKUNCI."
            )
        rec = RisetKasusNegatifModel(
            id=str(uuid.uuid4()),
            protokol_id=protokol.id,
            ringkasan=data.ringkasan,
            alasan_negatif=data.alasan_negatif,
            sumber_ref=data.sumber_ref,
            dibuat_oleh=dibuat_oleh,
            created_at=datetime.now(UTC),
        )
        self._s.add(rec)
        self._s.flush()
        self._s.refresh(rec)
        return _to_read(rec)

    def list_by_protokol(
        self, protokol_id: str, *, limit: int, offset: int
    ) -> tuple[list[RisetKasusNegatifRead], int]:
        """Daftar kasus negatif satu protokol, terlama dulu; 404 bila protokol tak ada."""
        self._protokol(protokol_id)
        m = RisetKasusNegatifModel
        cond = m.protokol_id == protokol_id
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(m.created_at, m.id).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total
