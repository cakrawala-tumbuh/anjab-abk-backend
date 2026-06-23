"""Implementasi `MataPelajaranService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryMataPelajaranService` TANPA mengubah kontrak Protocol —
signature & return type identik. Validasi & pesan error meniru PERSIS placeholder
in-memory (`NotFoundError` 404, `ConflictError` 409).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError
from ...models import MataPelajaranModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.mata_pelajaran import MataPelajaranCreate, MataPelajaranRead, MataPelajaranUpdate
from .mata_pelajaran import SEARCHABLE_FIELDS


def _field_map() -> FieldMap:
    m = MataPelajaranModel
    return {
        "id": FieldSpec(column=m.id),
        "kode": FieldSpec(column=m.kode),
        "nama": FieldSpec(column=m.nama),
        "kelompok": FieldSpec(column=m.kelompok),
        "aktif": FieldSpec(column=m.aktif),
    }


def _to_read(rec: MataPelajaranModel) -> MataPelajaranRead:
    return MataPelajaranRead(
        id=rec.id,
        kode=rec.kode,
        nama=rec.nama,
        kelompok=rec.kelompok,  # type: ignore[arg-type]
        deskripsi=rec.deskripsi,
        aktif=rec.aktif,
    )


class SqlMataPelajaranService:
    """`MataPelajaranService` berbasis PostgreSQL. Satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, mp_id: str) -> MataPelajaranModel:
        rec = self._s.get(MataPelajaranModel, mp_id)
        if rec is None:
            raise NotFoundError(f"Mata pelajaran '{mp_id}' tidak ditemukan.")
        return rec

    def _flush_checked(self, *, on_conflict: str) -> None:
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(on_conflict) from exc

    def list(self, *, limit: int, offset: int) -> tuple[list[MataPelajaranRead], int]:
        m = MataPelajaranModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(select(m).order_by(m.nama.asc()).limit(limit).offset(offset)).all()
        return [_to_read(r) for r in rows], total

    def get(self, mp_id: str) -> MataPelajaranRead:
        return _to_read(self._get_model(mp_id))

    def create(self, data: MataPelajaranCreate) -> MataPelajaranRead:
        exists = self._s.scalar(
            select(MataPelajaranModel.id).where(MataPelajaranModel.kode == data.kode)
        )
        if exists is not None:
            raise ConflictError(f"Mata pelajaran dengan kode '{data.kode}' sudah ada.")
        rec = MataPelajaranModel(
            id=f"mp_{uuid.uuid4().hex[:8]}",
            kode=data.kode,
            nama=data.nama,
            kelompok=data.kelompok,
            deskripsi=data.deskripsi,
            aktif=data.aktif,
        )
        self._s.add(rec)
        self._flush_checked(on_conflict=f"Mata pelajaran dengan kode '{data.kode}' sudah ada.")
        return _to_read(rec)

    def update(self, mp_id: str, data: MataPelajaranUpdate) -> MataPelajaranRead:
        rec = self._get_model(mp_id)
        changes = data.model_dump(exclude_unset=True)
        if "kode" in changes:
            clash = self._s.scalar(
                select(MataPelajaranModel.id).where(
                    MataPelajaranModel.kode == changes["kode"],
                    MataPelajaranModel.id != mp_id,
                )
            )
            if clash is not None:
                raise ConflictError(f"Mata pelajaran dengan kode '{changes['kode']}' sudah ada.")
        for key, value in changes.items():
            setattr(rec, key, value)
        self._flush_checked(on_conflict="Pembaruan melanggar batasan keunikan.")
        return _to_read(rec)

    def delete(self, mp_id: str) -> None:
        rec = self._get_model(mp_id)
        self._s.delete(rec)
        self._flush_checked(on_conflict="Tidak dapat menghapus mata pelajaran.")

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[MataPelajaranRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = MataPelajaranModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.nama.asc()]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total
