"""Implementasi `TugasPokokService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTugasPokokService` TANPA mengubah kontrak Protocol — signature
method identik, sehingga router, skema, dan error envelope tidak ikut berubah.

`nama` unik global. Relasi M2M ke Jabatan dikelola lewat `TiTugasPokokModel.jabatan_links`
(list `TiTugasPokokJabatanModel`); `jabatan_ids` dibaca dari property model.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError
from ...models import TiTugasPokokJabatanModel, TiTugasPokokModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.tugas_pokok import TugasPokokCreate, TugasPokokRead, TugasPokokUpdate

# Sumber tunggal whitelist (didefinisikan di seam placeholder InMemory).
from .tugas_pokok import SEARCHABLE_FIELDS


def _tugas_pokok_field_map() -> FieldMap:
    return {
        "id": FieldSpec(column=TiTugasPokokModel.id),
        "nama": FieldSpec(column=TiTugasPokokModel.nama),
        "created_at": FieldSpec(
            column=TiTugasPokokModel.created_at, order_column=TiTugasPokokModel.created_at
        ),
    }


def _to_read(rec: TiTugasPokokModel) -> TugasPokokRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return TugasPokokRead(
        id=rec.id,
        jabatan_ids=list(rec.jabatan_ids),
        nama=rec.nama,
        created_at=created,
    )


class SqlTugasPokokService:
    """`TugasPokokService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, tp_id: str) -> TiTugasPokokModel:
        rec = self._s.get(TiTugasPokokModel, tp_id)
        if rec is None:
            raise NotFoundError(f"TugasPokok '{tp_id}' tidak ditemukan.")
        return rec

    def _flush_checked(self, *, on_conflict: str) -> None:
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(on_conflict) from exc

    def list(self, *, limit: int, offset: int) -> tuple[list[TugasPokokRead], int]:
        total = self._s.scalar(select(func.count()).select_from(TiTugasPokokModel)) or 0
        rows = self._s.scalars(
            select(TiTugasPokokModel).order_by(TiTugasPokokModel.nama).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def get(self, tp_id: str) -> TugasPokokRead:
        return _to_read(self._get_model(tp_id))

    def create(self, data: TugasPokokCreate) -> TugasPokokRead:
        exists = self._s.scalar(
            select(TiTugasPokokModel.id).where(TiTugasPokokModel.nama == data.nama)
        )
        if exists is not None:
            raise ConflictError(f"TugasPokok dengan nama '{data.nama}' sudah ada.")
        rec = TiTugasPokokModel(
            id=f"tp_{uuid.uuid4().hex[:8]}",
            nama=data.nama,
            jabatan_links=[
                TiTugasPokokJabatanModel(jabatan_id=j) for j in dict.fromkeys(data.jabatan_ids)
            ],
        )
        self._s.add(rec)
        self._flush_checked(on_conflict=f"TugasPokok dengan nama '{data.nama}' sudah ada.")
        return _to_read(rec)

    def update(self, tp_id: str, data: TugasPokokUpdate) -> TugasPokokRead:
        rec = self._get_model(tp_id)
        changes = data.model_dump(exclude_unset=True)
        if "nama" in changes and changes["nama"] != rec.nama:
            clash = self._s.scalar(
                select(TiTugasPokokModel.id).where(
                    TiTugasPokokModel.nama == changes["nama"], TiTugasPokokModel.id != tp_id
                )
            )
            if clash is not None:
                raise ConflictError(f"TugasPokok dengan nama '{changes['nama']}' sudah ada.")
            rec.nama = changes["nama"]
        if "jabatan_ids" in changes:
            desired = list(dict.fromkeys(changes["jabatan_ids"]))
            current = {link.jabatan_id: link for link in rec.jabatan_links}
            for jid, link in list(current.items()):
                if jid not in desired:
                    rec.jabatan_links.remove(link)
            for jid in desired:
                if jid not in current:
                    rec.jabatan_links.append(TiTugasPokokJabatanModel(jabatan_id=jid))
        self._flush_checked(on_conflict="Pembaruan melanggar batasan keunikan.")
        return _to_read(rec)

    def delete(self, tp_id: str) -> None:
        rec = self._get_model(tp_id)
        self._s.delete(rec)  # cascade menghapus baris jabatan
        self._flush_checked(on_conflict="Tidak dapat menghapus TugasPokok.")

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[TugasPokokRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        field_map = _tugas_pokok_field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [TiTugasPokokModel.nama]
        total = self._s.scalar(select(func.count()).select_from(TiTugasPokokModel).where(cond)) or 0
        rows = self._s.scalars(
            select(TiTugasPokokModel).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total
