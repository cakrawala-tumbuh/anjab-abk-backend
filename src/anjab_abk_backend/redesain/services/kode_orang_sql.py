"""Implementasi `KodeOrangService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError
from ...models import KODE_ORANG_SEQ, PartisipanModel, RedesainKodeOrangModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.kode_orang import KodeOrangCreate, KodeOrangRead, KodeOrangUpdate
from .kode_orang import SEARCHABLE_FIELDS
from .riwayat import RiwayatService

ENTITAS = "kode_orang"


def format_kode(nomor: int) -> str:
    """Format nomor urut sequence menjadi kode pseudonim.

    Args:
        nomor: Nilai `nextval` sequence (>= 1).

    Returns:
        `O-` + nomor ber-nol-depan minimal 4 digit (`O-0001`); di atas 9999 tidak dipotong.
    """
    return f"O-{nomor:04d}"


def _field_map() -> FieldMap:
    m = RedesainKodeOrangModel
    return {
        "id": FieldSpec(column=m.id),
        "kode": FieldSpec(column=m.kode),
        "partisipan_id": FieldSpec(column=m.partisipan_id),
        "keterangan_peran": FieldSpec(column=m.keterangan_peran),
        "created_at": FieldSpec(column=m.created_at, order_column=m.created_at),
    }


def _to_read(rec: RedesainKodeOrangModel) -> KodeOrangRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return KodeOrangRead(
        id=rec.id,
        kode=rec.kode,
        partisipan_id=rec.partisipan_id,
        keterangan_peran=rec.keterangan_peran,
        created_at=created,
    )


def _snapshot(r: KodeOrangRead) -> dict[str, object]:
    return {
        "kode": r.kode,
        "partisipan_id": r.partisipan_id,
        "keterangan_peran": r.keterangan_peran,
    }


class SqlKodeOrangService:
    """`KodeOrangService` berbasis PostgreSQL; terikat satu `Session` per request."""

    def __init__(self, session: Session, riwayat: RiwayatService) -> None:
        self._s = session
        self._riwayat = riwayat

    def _baru(
        self, partisipan_id: str | None, keterangan_peran: str | None
    ) -> RedesainKodeOrangModel:
        nomor = self._s.scalar(KODE_ORANG_SEQ.next_value())
        rec = RedesainKodeOrangModel(
            id=str(uuid.uuid4()),
            kode=format_kode(int(nomor)),
            partisipan_id=partisipan_id,
            keterangan_peran=keterangan_peran,
        )
        self._s.add(rec)
        self._s.flush()
        return rec

    def _by_partisipan(self, partisipan_id: str) -> RedesainKodeOrangModel | None:
        m = RedesainKodeOrangModel
        return self._s.scalars(select(m).where(m.partisipan_id == partisipan_id)).first()

    def untuk_partisipan(self, partisipan_id: str) -> KodeOrangRead:
        """Ambil kode partisipan; buat (get-or-create) bila belum ada.

        Args:
            partisipan_id: ID partisipan yang sudah ada.

        Returns:
            Baris kode orang partisipan itu; dua panggilan berturut-turut menghasilkan kode sama.

        Raises:
            NotFoundError: Partisipan tidak ada.
        """
        rec = self._by_partisipan(partisipan_id)
        if rec is not None:
            return _to_read(rec)
        if self._s.get(PartisipanModel, partisipan_id) is None:
            raise NotFoundError(f"Partisipan '{partisipan_id}' tidak ditemukan.")
        try:
            with self._s.begin_nested():
                rec = self._baru(partisipan_id, None)
        except IntegrityError:
            # Balapan: request lain sudah membuatnya; baca hasilnya.
            rec = self._by_partisipan(partisipan_id)
            if rec is None:
                raise
            return _to_read(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "create", None, _snapshot(read), read.kode)
        return read

    def create(self, data: KodeOrangCreate, *, pelaku_kode_orang: str | None) -> KodeOrangRead:
        """Daftarkan orang baru (narasumber atau partisipan) dan catat riwayat.

        Raises:
            NotFoundError: `partisipan_id` diberikan tetapi tidak ada.
            ConflictError: `partisipan_id` sudah punya kode.
        """
        if data.partisipan_id is not None:
            if self._s.get(PartisipanModel, data.partisipan_id) is None:
                raise NotFoundError(f"Partisipan '{data.partisipan_id}' tidak ditemukan.")
            if self._by_partisipan(data.partisipan_id) is not None:
                raise ConflictError("Partisipan ini sudah memiliki kode orang.")
        rec = self._baru(data.partisipan_id, data.keterangan_peran)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "create", None, _snapshot(read), pelaku_kode_orang)
        return read

    def _get_model(self, kode_orang_id: str) -> RedesainKodeOrangModel:
        rec = self._s.get(RedesainKodeOrangModel, kode_orang_id)
        if rec is None:
            raise NotFoundError(f"Kode orang '{kode_orang_id}' tidak ditemukan.")
        return rec

    def get(self, kode_orang_id: str) -> KodeOrangRead:
        """Ambil satu baris; `NotFoundError` (404) bila tak ada."""
        return _to_read(self._get_model(kode_orang_id))

    def list(self, *, limit: int, offset: int) -> tuple[list[KodeOrangRead], int]:
        """Daftar berurutan menurut waktu pembuatan lalu `kode`."""
        m = RedesainKodeOrangModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(
            select(m).order_by(m.created_at, m.kode).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[KodeOrangRead], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = RedesainKodeOrangModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.created_at, m.kode]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def update(
        self, kode_orang_id: str, data: KodeOrangUpdate, *, pelaku_kode_orang: str | None
    ) -> KodeOrangRead:
        """Ubah `keterangan_peran` dan catat riwayat.

        Raises:
            NotFoundError: Baris tidak ada.
        """
        rec = self._get_model(kode_orang_id)
        sebelum = _snapshot(_to_read(rec))
        if "keterangan_peran" in data.model_fields_set:
            rec.keterangan_peran = data.keterangan_peran
        self._s.flush()
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "update", sebelum, _snapshot(read), pelaku_kode_orang)
        return read
