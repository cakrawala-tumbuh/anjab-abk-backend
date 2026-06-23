"""Implementasi `SMEPanelService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemorySMEPanelService` (placeholder seam) TANPA mengubah kontrak
`SMEPanelService` (Protocol) — signature method identik, sehingga router, skema,
dan error envelope tidak ikut berubah.

Pemetaan error ke hierarki `AppError`:
- baris/anggota tak ada       → `NotFoundError` (404)
- `jabatan_id` duplikat        → `ConflictError` (409, satu panel per jabatan)
- anggota duplikat             → `ConflictError` (409)

Anggota panel dikelola lewat relasi `SMEPanelModel.anggota` (list
`SMEPanelAnggotaModel`); `partisipan_ids` dibaca dari property model.

Validasi "koordinator harus anggota" pada `update` TIDAK dilakukan di sini —
InMemory pun tidak melakukannya (ditangani di router). Service hanya men-`setattr`
field yang dikirim, persis InMemory.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError
from ...models import SMEPanelAnggotaModel, SMEPanelModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.sme_panel import SMEPanelCreate, SMEPanelRead, SMEPanelUpdate

# Sumber tunggal whitelist (didefinisikan di seam placeholder InMemory).
from .sme_panel import SEARCHABLE_FIELDS


def sme_panel_field_map() -> FieldMap:
    """Petakan field ter-whitelist → kolom PostgreSQL."""
    return {
        "id": FieldSpec(column=SMEPanelModel.id),
        "jabatan_id": FieldSpec(column=SMEPanelModel.jabatan_id),
        "aktif": FieldSpec(column=SMEPanelModel.aktif),
        "created_at": FieldSpec(
            column=SMEPanelModel.created_at, order_column=SMEPanelModel.created_at
        ),
    }


def _to_read(rec: SMEPanelModel) -> SMEPanelRead:
    """Petakan model penyimpanan → skema API (skema ≠ model penyimpanan)."""
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return SMEPanelRead(
        id=rec.id,
        jabatan_id=rec.jabatan_id,
        partisipan_ids=list(rec.partisipan_ids),
        koordinator_id=rec.koordinator_id,
        aktif=rec.aktif,
        created_at=created,
    )


class SqlSMEPanelService:
    """`SMEPanelService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, panel_id: str) -> SMEPanelModel:
        rec = self._s.get(SMEPanelModel, panel_id)
        if rec is None:
            raise NotFoundError(f"SME panel '{panel_id}' tidak ditemukan.")
        return rec

    def _flush_checked(self, *, on_conflict: str) -> None:
        """Flush dalam SAVEPOINT; petakan `IntegrityError` (duplikat unik) → 409."""
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(on_conflict) from exc

    def list(self, *, limit: int, offset: int) -> tuple[list[SMEPanelRead], int]:
        total = self._s.scalar(select(func.count()).select_from(SMEPanelModel)) or 0
        rows = self._s.scalars(
            select(SMEPanelModel).order_by(SMEPanelModel.created_at).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def get(self, panel_id: str) -> SMEPanelRead:
        return _to_read(self._get_model(panel_id))

    def create(self, data: SMEPanelCreate) -> SMEPanelRead:
        # Pre-cek jabatan_id untuk pesan ramah; unique constraint backstop balapan.
        exists = self._s.scalar(
            select(SMEPanelModel.id).where(SMEPanelModel.jabatan_id == data.jabatan_id)
        )
        if exists is not None:
            raise ConflictError(f"SME panel untuk jabatan '{data.jabatan_id}' sudah ada.")
        rec = SMEPanelModel(
            id=f"sme_{uuid.uuid4().hex[:8]}",
            jabatan_id=data.jabatan_id,
            aktif=data.aktif,
        )
        self._s.add(rec)
        self._flush_checked(on_conflict=f"SME panel untuk jabatan '{data.jabatan_id}' sudah ada.")
        return _to_read(rec)

    def update(self, panel_id: str, data: SMEPanelUpdate) -> SMEPanelRead:
        rec = self._get_model(panel_id)
        changes = data.model_dump(exclude_unset=True)  # semantik PATCH yang benar
        for key, value in changes.items():
            setattr(rec, key, value)
        self._flush_checked(on_conflict="Pembaruan melanggar batasan keunikan.")
        return _to_read(rec)

    def delete(self, panel_id: str) -> None:
        rec = self._get_model(panel_id)
        self._s.delete(rec)  # cascade menghapus baris anggota
        self._flush_checked(on_conflict="Tidak dapat menghapus SME panel.")

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[SMEPanelRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)  # 422 bila field asing
        field_map = sme_panel_field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [SMEPanelModel.created_at]
        total = self._s.scalar(select(func.count()).select_from(SMEPanelModel).where(cond)) or 0
        rows = self._s.scalars(
            select(SMEPanelModel).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def add_anggota(self, panel_id: str, partisipan_id: str) -> SMEPanelRead:
        rec = self._get_model(panel_id)
        if partisipan_id in rec.partisipan_ids:
            raise ConflictError(f"Partisipan '{partisipan_id}' sudah menjadi anggota panel ini.")
        rec.anggota.append(SMEPanelAnggotaModel(partisipan_id=partisipan_id))
        self._flush_checked(
            on_conflict=f"Partisipan '{partisipan_id}' sudah menjadi anggota panel ini."
        )
        return _to_read(rec)

    def remove_anggota(self, panel_id: str, partisipan_id: str) -> SMEPanelRead:
        rec = self._get_model(panel_id)
        target = next((a for a in rec.anggota if a.partisipan_id == partisipan_id), None)
        if target is None:
            raise NotFoundError(f"Partisipan '{partisipan_id}' bukan anggota panel ini.")
        rec.anggota.remove(target)  # delete-orphan menghapus baris
        if rec.koordinator_id == partisipan_id:
            rec.koordinator_id = None
        self._flush_checked(on_conflict="Tidak dapat menghapus anggota panel.")
        return _to_read(rec)
