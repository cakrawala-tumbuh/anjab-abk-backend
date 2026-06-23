"""Implementasi `TsSesiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTsSesiService` TANPA mengubah kontrak Protocol — signature
method identik, sehingga router, skema, error envelope, dan test kontrak HTTP
tidak ikut berubah.

`TsSesiService` tidak punya operasi `search`, jadi tidak ada FieldMap di sini.
State machine DRAFT→OPEN→CLOSED→ANALYZED dipakai ULANG dari `.sesi`.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import NotFoundError, ValidationAppError
from ...models import TsSesiModel
from ..schemas.sesi import StatusSesi, TsSesiCreate, TsSesiRead, TsSesiUpdate

# Sumber tunggal state machine.
from .sesi import _VALID_TRANSITIONS


def _to_read(rec: TsSesiModel) -> TsSesiRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return TsSesiRead(
        id=rec.id,
        jabatan_id=rec.jabatan_id,
        periode=rec.periode,
        status=rec.status,  # type: ignore[arg-type]
        catatan=rec.catatan,
        created_at=created,
    )


class SqlTsSesiService:
    """`TsSesiService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, sesi_id: str) -> TsSesiModel:
        rec = self._s.get(TsSesiModel, sesi_id)
        if rec is None:
            raise NotFoundError(f"Sesi Time Study '{sesi_id}' tidak ditemukan.")
        return rec

    def list(self, *, limit: int, offset: int) -> tuple[list[TsSesiRead], int]:
        total = self._s.scalar(select(func.count()).select_from(TsSesiModel)) or 0
        rows = self._s.scalars(
            select(TsSesiModel).order_by(TsSesiModel.created_at.desc()).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def get(self, sesi_id: str) -> TsSesiRead:
        return _to_read(self._get_model(sesi_id))

    def create(self, data: TsSesiCreate) -> TsSesiRead:
        rec = TsSesiModel(
            id=f"tses_{uuid.uuid4().hex[:8]}",
            jabatan_id=data.jabatan_id,
            periode=data.periode,
            status="DRAFT",
            catatan=data.catatan,
        )
        self._s.add(rec)
        self._s.flush()
        return _to_read(rec)

    def update(self, sesi_id: str, data: TsSesiUpdate) -> TsSesiRead:
        rec = self._get_model(sesi_id)
        if rec.status != "DRAFT":
            raise ValidationAppError("Sesi hanya dapat diperbarui saat berstatus DRAFT.")
        changes = data.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(rec, key, value)
        self._s.flush()
        return _to_read(rec)

    def delete(self, sesi_id: str) -> None:
        rec = self._get_model(sesi_id)
        if rec.status != "DRAFT":
            raise ValidationAppError("Sesi hanya dapat dihapus saat berstatus DRAFT.")
        self._s.delete(rec)
        self._s.flush()

    def transition(self, sesi_id: str, target: StatusSesi) -> TsSesiRead:
        rec = self._get_model(sesi_id)
        expected = _VALID_TRANSITIONS.get(rec.status)  # type: ignore[arg-type]
        if expected != target:
            raise ValidationAppError(
                f"Transisi dari '{rec.status}' ke '{target}' tidak valid."
                f" Transisi yang diizinkan: '{rec.status}' → '{expected}'."
            )
        rec.status = target
        self._s.flush()
        return _to_read(rec)
