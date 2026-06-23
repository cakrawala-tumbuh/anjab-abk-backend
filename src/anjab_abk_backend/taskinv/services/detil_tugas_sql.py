"""Implementasi `DetilTugasService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryDetilTugasService` TANPA mengubah kontrak Protocol.

Validasi subset jabatan (jabatan_ids DetilTugas ⊆ jabatan_ids TugasPokok induk)
direplikasi langsung lewat query DB ke tabel `ti_tugas_pokok_jabatan`, alih-alih
memanggil service lain. Parameter `tp_svc` dipertahankan agar signature kompatibel
dengan InMemory, tetapi tidak diperlukan oleh implementasi SQL.
"""

from __future__ import annotations

import uuid
from datetime import UTC
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import TiDetilTugasJabatanModel, TiDetilTugasModel, TiTugasPokokModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.detil_tugas import DetilTugasCreate, DetilTugasRead, DetilTugasUpdate

# Sumber tunggal whitelist (didefinisikan di seam placeholder InMemory).
from .detil_tugas import SEARCHABLE_FIELDS


def _detil_tugas_field_map() -> FieldMap:
    return {
        "id": FieldSpec(column=TiDetilTugasModel.id),
        "nama": FieldSpec(column=TiDetilTugasModel.nama),
        "tugas_pokok_id": FieldSpec(column=TiDetilTugasModel.tugas_pokok_id),
        "created_at": FieldSpec(
            column=TiDetilTugasModel.created_at, order_column=TiDetilTugasModel.created_at
        ),
    }


def _to_read(rec: TiDetilTugasModel) -> DetilTugasRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return DetilTugasRead(
        id=rec.id,
        nama=rec.nama,
        tugas_pokok_id=rec.tugas_pokok_id,
        jabatan_ids=list(rec.jabatan_ids),
        created_at=created,
    )


class SqlDetilTugasService:
    """`DetilTugasService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session, *, tp_svc: Any | None = None) -> None:
        self._s = session
        self._tp = tp_svc  # tidak dipakai; validasi subset langsung lewat DB.

    def _get_model(self, dt_id: str) -> TiDetilTugasModel:
        rec = self._s.get(TiDetilTugasModel, dt_id)
        if rec is None:
            raise NotFoundError(f"DetilTugas '{dt_id}' tidak ditemukan.")
        return rec

    def _flush_checked(self, *, on_conflict: str) -> None:
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(on_conflict) from exc

    def _validate_jabatan_subset(self, jabatan_ids: list[str], tugas_pokok_id: str) -> None:
        tp = self._s.get(TiTugasPokokModel, tugas_pokok_id)
        if tp is None:
            raise NotFoundError(f"TugasPokok '{tugas_pokok_id}' tidak ditemukan.")
        tp_jabatan = set(tp.jabatan_ids)
        invalid = [jid for jid in jabatan_ids if jid not in tp_jabatan]
        if invalid:
            raise ValidationAppError(
                f"Jabatan {invalid} bukan bagian dari jabatan_ids TugasPokok '{tugas_pokok_id}'."
            )

    def list(self, *, limit: int, offset: int) -> tuple[list[DetilTugasRead], int]:
        total = self._s.scalar(select(func.count()).select_from(TiDetilTugasModel)) or 0
        rows = self._s.scalars(
            select(TiDetilTugasModel)
            .order_by(TiDetilTugasModel.tugas_pokok_id, TiDetilTugasModel.nama)
            .limit(limit)
            .offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def get(self, dt_id: str) -> DetilTugasRead:
        return _to_read(self._get_model(dt_id))

    def create(self, data: DetilTugasCreate) -> DetilTugasRead:
        self._validate_jabatan_subset(data.jabatan_ids, data.tugas_pokok_id)
        rec = TiDetilTugasModel(
            id=f"dt_{uuid.uuid4().hex[:8]}",
            nama=data.nama,
            tugas_pokok_id=data.tugas_pokok_id,
            jabatan_links=[
                TiDetilTugasJabatanModel(jabatan_id=j) for j in dict.fromkeys(data.jabatan_ids)
            ],
        )
        self._s.add(rec)
        self._flush_checked(on_conflict="Pembuatan melanggar batasan keunikan.")
        return _to_read(rec)

    def update(self, dt_id: str, data: DetilTugasUpdate) -> DetilTugasRead:
        rec = self._get_model(dt_id)
        changes = data.model_dump(exclude_unset=True)
        new_tp_id = changes.get("tugas_pokok_id", rec.tugas_pokok_id)
        new_jabatan_ids = changes.get("jabatan_ids", list(rec.jabatan_ids))
        if "jabatan_ids" in changes or "tugas_pokok_id" in changes:
            self._validate_jabatan_subset(new_jabatan_ids, new_tp_id)
        if "nama" in changes:
            rec.nama = changes["nama"]
        if "tugas_pokok_id" in changes:
            rec.tugas_pokok_id = changes["tugas_pokok_id"]
        if "jabatan_ids" in changes:
            desired = list(dict.fromkeys(changes["jabatan_ids"]))
            current = {link.jabatan_id: link for link in rec.jabatan_links}
            for jid, link in list(current.items()):
                if jid not in desired:
                    rec.jabatan_links.remove(link)
            for jid in desired:
                if jid not in current:
                    rec.jabatan_links.append(TiDetilTugasJabatanModel(jabatan_id=jid))
        self._flush_checked(on_conflict="Pembaruan melanggar batasan keunikan.")
        return _to_read(rec)

    def delete(self, dt_id: str) -> None:
        rec = self._get_model(dt_id)
        self._s.delete(rec)  # cascade menghapus baris jabatan
        self._flush_checked(on_conflict="Tidak dapat menghapus DetilTugas.")

    def list_by_tugas_pokok(self, tp_id: str) -> list[DetilTugasRead]:
        rows = self._s.scalars(
            select(TiDetilTugasModel)
            .where(TiDetilTugasModel.tugas_pokok_id == tp_id)
            .order_by(TiDetilTugasModel.nama)
        ).all()
        return [_to_read(r) for r in rows]

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[DetilTugasRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        field_map = _detil_tugas_field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [
            TiDetilTugasModel.tugas_pokok_id,
            TiDetilTugasModel.nama,
        ]
        total = self._s.scalar(select(func.count()).select_from(TiDetilTugasModel).where(cond)) or 0
        rows = self._s.scalars(
            select(TiDetilTugasModel).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total
