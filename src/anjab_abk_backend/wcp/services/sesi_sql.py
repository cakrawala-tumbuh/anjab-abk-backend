"""Implementasi `WcpSesiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryWcpSesiService` TANPA mengubah kontrak Protocol — signature
method identik, sehingga router, skema, error envelope, dan test kontrak HTTP
tidak ikut berubah.

Whitelist field search dipakai ULANG dari `.sesi.SEARCHABLE_FIELDS`
(satu sumber), lalu dipetakan ke kolom lewat `domain_sql.FieldSpec`.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import NotFoundError, ValidationAppError
from ...models import WcpSesiModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.sesi import StatusSesi, WcpSesiCreate, WcpSesiRead, WcpSesiUpdate

# Sumber tunggal whitelist & state machine.
from .sesi import _ERR_NON_DRAFT, _VALID_TRANSITIONS, SEARCHABLE_FIELDS


def _sesi_field_map() -> FieldMap:
    return {
        "id": FieldSpec(column=WcpSesiModel.id),
        "periode": FieldSpec(column=WcpSesiModel.periode),
        "status": FieldSpec(column=WcpSesiModel.status),
        "created_at": FieldSpec(
            column=WcpSesiModel.created_at, order_column=WcpSesiModel.created_at
        ),
    }


def _to_read(rec: WcpSesiModel) -> WcpSesiRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return WcpSesiRead(
        id=rec.id,
        periode=rec.periode,
        status=rec.status,  # type: ignore[arg-type]
        min_responden=rec.min_responden,
        max_responden=rec.max_responden,
        catatan=rec.catatan,
        created_at=created,
    )


class SqlWcpSesiService:
    """`WcpSesiService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, sesi_id: str) -> WcpSesiModel:
        rec = self._s.get(WcpSesiModel, sesi_id)
        if rec is None:
            raise NotFoundError(f"Sesi WCP '{sesi_id}' tidak ditemukan.")
        return rec

    def list(self, *, limit: int, offset: int) -> tuple[list[WcpSesiRead], int]:
        total = self._s.scalar(select(func.count()).select_from(WcpSesiModel)) or 0
        rows = self._s.scalars(
            select(WcpSesiModel)
            .order_by(WcpSesiModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def get(self, sesi_id: str) -> WcpSesiRead:
        return _to_read(self._get_model(sesi_id))

    def create(self, data: WcpSesiCreate) -> WcpSesiRead:
        if data.min_responden > data.max_responden:
            raise ValidationAppError("min_responden tidak boleh lebih besar dari max_responden.")
        rec = WcpSesiModel(
            id=f"wses_{uuid.uuid4().hex[:8]}",
            periode=data.periode,
            status="DRAFT",
            min_responden=data.min_responden,
            max_responden=data.max_responden,
            catatan=data.catatan,
        )
        self._s.add(rec)
        self._s.flush()
        return _to_read(rec)

    def update(self, sesi_id: str, data: WcpSesiUpdate) -> WcpSesiRead:
        rec = self._get_model(sesi_id)
        if rec.status != "DRAFT":
            raise ValidationAppError("Sesi hanya dapat diperbarui saat berstatus DRAFT.")
        changes = data.model_dump(exclude_unset=True)
        new_min = changes.get("min_responden", rec.min_responden)
        new_max = changes.get("max_responden", rec.max_responden)
        if new_min > new_max:
            raise ValidationAppError("min_responden tidak boleh lebih besar dari max_responden.")
        for key, value in changes.items():
            setattr(rec, key, value)
        self._s.flush()
        return _to_read(rec)

    def delete(self, sesi_id: str, *, paksa: bool = False) -> None:
        rec = self._get_model(sesi_id)
        if rec.status != "DRAFT" and not paksa:
            raise ValidationAppError(_ERR_NON_DRAFT)
        self._s.delete(rec)
        self._s.flush()
        self._s.expire_all()

    def transition(self, sesi_id: str, target: StatusSesi) -> WcpSesiRead:
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

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[WcpSesiRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        field_map = _sesi_field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [WcpSesiModel.created_at.desc()]
        total = self._s.scalar(select(func.count()).select_from(WcpSesiModel).where(cond)) or 0
        rows = self._s.scalars(
            select(WcpSesiModel).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total
