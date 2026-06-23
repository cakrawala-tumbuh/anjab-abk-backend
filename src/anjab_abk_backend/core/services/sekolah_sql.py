"""Implementasi `SekolahService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemorySekolahService` TANPA mengubah kontrak Protocol — signature &
return type identik. Validasi & pesan error meniru PERSIS placeholder in-memory
(`NotFoundError` 404, `ConflictError` 409). `created_at` (TIMESTAMPTZ) terisi via
default Python setelah `flush()`.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError
from ...models import SekolahModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.sekolah import SekolahCreate, SekolahRead, SekolahUpdate
from .sekolah import SEARCHABLE_FIELDS


def _field_map() -> FieldMap:
    m = SekolahModel
    return {
        "id": FieldSpec(column=m.id),
        "nama": FieldSpec(column=m.nama),
        "npsn": FieldSpec(column=m.npsn),
        "jenjang_pendidikan_id": FieldSpec(column=m.jenjang_pendidikan_id),
        "kota": FieldSpec(column=m.kota),
        "provinsi": FieldSpec(column=m.provinsi),
        "aktif": FieldSpec(column=m.aktif),
        "created_at": FieldSpec(column=m.created_at, order_column=m.created_at),
    }


def _to_read(rec: SekolahModel) -> SekolahRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return SekolahRead(
        id=rec.id,
        nama=rec.nama,
        npsn=rec.npsn,
        jenjang_pendidikan_id=rec.jenjang_pendidikan_id,
        kota=rec.kota,
        provinsi=rec.provinsi,
        aktif=rec.aktif,
        created_at=created,
    )


class SqlSekolahService:
    """`SekolahService` berbasis PostgreSQL. Satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, sekolah_id: str) -> SekolahModel:
        rec = self._s.get(SekolahModel, sekolah_id)
        if rec is None:
            raise NotFoundError(f"Sekolah '{sekolah_id}' tidak ditemukan.")
        return rec

    def _flush_checked(self, *, on_conflict: str) -> None:
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(on_conflict) from exc

    def list(self, *, limit: int, offset: int) -> tuple[list[SekolahRead], int]:
        m = SekolahModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(select(m).order_by(m.nama.asc()).limit(limit).offset(offset)).all()
        return [_to_read(r) for r in rows], total

    def get(self, sekolah_id: str) -> SekolahRead:
        return _to_read(self._get_model(sekolah_id))

    def create(self, data: SekolahCreate) -> SekolahRead:
        if data.npsn:
            exists = self._s.scalar(select(SekolahModel.id).where(SekolahModel.npsn == data.npsn))
            if exists is not None:
                raise ConflictError(f"Sekolah dengan NPSN '{data.npsn}' sudah ada.")
        rec = SekolahModel(
            id=f"skl_{uuid.uuid4().hex[:8]}",
            nama=data.nama,
            npsn=data.npsn,
            jenjang_pendidikan_id=data.jenjang_pendidikan_id,
            kota=data.kota,
            provinsi=data.provinsi,
            aktif=data.aktif,
        )
        self._s.add(rec)
        self._flush_checked(on_conflict=f"Sekolah dengan NPSN '{data.npsn}' sudah ada.")
        return _to_read(rec)

    def update(self, sekolah_id: str, data: SekolahUpdate) -> SekolahRead:
        rec = self._get_model(sekolah_id)
        changes = data.model_dump(exclude_unset=True)
        if "npsn" in changes and changes["npsn"]:
            clash = self._s.scalar(
                select(SekolahModel.id).where(
                    SekolahModel.npsn == changes["npsn"],
                    SekolahModel.id != sekolah_id,
                )
            )
            if clash is not None:
                raise ConflictError(f"Sekolah dengan NPSN '{changes['npsn']}' sudah ada.")
        for key, value in changes.items():
            setattr(rec, key, value)
        self._flush_checked(on_conflict="Pembaruan melanggar batasan keunikan.")
        return _to_read(rec)

    def delete(self, sekolah_id: str) -> None:
        rec = self._get_model(sekolah_id)
        self._s.delete(rec)
        self._flush_checked(on_conflict="Tidak dapat menghapus sekolah.")

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[SekolahRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = SekolahModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.nama.asc()]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total
