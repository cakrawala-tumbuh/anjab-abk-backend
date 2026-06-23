"""Implementasi `JenjangPendidikanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryJenjangPendidikanService` TANPA mengubah kontrak Protocol —
signature & return type identik. Validasi & pesan error meniru PERSIS placeholder
in-memory (`NotFoundError` 404, `ConflictError` 409).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError
from ...models import JenjangPendidikanModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.jenjang_pendidikan import (
    JenjangPendidikanCreate,
    JenjangPendidikanRead,
    JenjangPendidikanUpdate,
)
from .jenjang_pendidikan import SEARCHABLE_FIELDS


def _field_map() -> FieldMap:
    m = JenjangPendidikanModel
    return {
        "id": FieldSpec(column=m.id),
        "kode": FieldSpec(column=m.kode),
        "nama": FieldSpec(column=m.nama),
        "urutan": FieldSpec(column=m.urutan),
        "aktif": FieldSpec(column=m.aktif),
    }


def _to_read(rec: JenjangPendidikanModel) -> JenjangPendidikanRead:
    return JenjangPendidikanRead(
        id=rec.id,
        kode=rec.kode,
        nama=rec.nama,
        urutan=rec.urutan,
        aktif=rec.aktif,
    )


class SqlJenjangPendidikanService:
    """`JenjangPendidikanService` berbasis PostgreSQL. Satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, jp_id: str) -> JenjangPendidikanModel:
        rec = self._s.get(JenjangPendidikanModel, jp_id)
        if rec is None:
            raise NotFoundError(f"Jenjang pendidikan '{jp_id}' tidak ditemukan.")
        return rec

    def _flush_checked(self, *, on_conflict: str) -> None:
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(on_conflict) from exc

    def list(self, *, limit: int, offset: int) -> tuple[list[JenjangPendidikanRead], int]:
        m = JenjangPendidikanModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(
            select(m).order_by(m.urutan.asc(), m.nama.asc()).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def get(self, jp_id: str) -> JenjangPendidikanRead:
        return _to_read(self._get_model(jp_id))

    def create(self, data: JenjangPendidikanCreate) -> JenjangPendidikanRead:
        exists = self._s.scalar(
            select(JenjangPendidikanModel.id).where(JenjangPendidikanModel.kode == data.kode)
        )
        if exists is not None:
            raise ConflictError(f"Jenjang dengan kode '{data.kode}' sudah ada.")
        rec = JenjangPendidikanModel(
            id=f"jp_{uuid.uuid4().hex[:8]}",
            kode=data.kode,
            nama=data.nama,
            urutan=data.urutan,
            aktif=data.aktif,
        )
        self._s.add(rec)
        self._flush_checked(on_conflict=f"Jenjang dengan kode '{data.kode}' sudah ada.")
        return _to_read(rec)

    def update(self, jp_id: str, data: JenjangPendidikanUpdate) -> JenjangPendidikanRead:
        rec = self._get_model(jp_id)
        changes = data.model_dump(exclude_unset=True)
        if "kode" in changes:
            clash = self._s.scalar(
                select(JenjangPendidikanModel.id).where(
                    JenjangPendidikanModel.kode == changes["kode"],
                    JenjangPendidikanModel.id != jp_id,
                )
            )
            if clash is not None:
                raise ConflictError(f"Jenjang dengan kode '{changes['kode']}' sudah ada.")
        for key, value in changes.items():
            setattr(rec, key, value)
        self._flush_checked(on_conflict="Pembaruan melanggar batasan keunikan.")
        return _to_read(rec)

    def delete(self, jp_id: str) -> None:
        rec = self._get_model(jp_id)
        self._s.delete(rec)
        self._flush_checked(on_conflict="Tidak dapat menghapus jenjang pendidikan.")

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[JenjangPendidikanRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = JenjangPendidikanModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.urutan.asc(), m.nama.asc()]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total
