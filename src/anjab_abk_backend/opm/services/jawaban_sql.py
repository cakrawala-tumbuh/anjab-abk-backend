"""Implementasi `OpmJawabanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

Uniqueness `(responden_id, task_kode)` dijaga oleh `UniqueConstraint` di model;
flush dalam SAVEPOINT memetakan `IntegrityError` (balapan) → `ConflictError`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError
from ...models import OpmJawabanModel
from ..schemas.jawaban import OpmJawabanBulkCreate, OpmJawabanRead
from .jawaban import _validate_task_set


def _to_read(rec: OpmJawabanModel) -> OpmJawabanRead:
    return OpmJawabanRead(
        id=rec.id,
        responden_id=rec.responden_id,
        task_kode=rec.task_kode,
        importance=rec.importance,
        frequency=rec.frequency,
        criticality=rec.criticality,
        catatan=rec.catatan,
    )


class SqlOpmJawabanService:
    """`OpmJawabanService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def list_by_responden(self, responden_id: str) -> list[OpmJawabanRead]:
        rows = self._s.scalars(
            select(OpmJawabanModel)
            .where(OpmJawabanModel.responden_id == responden_id)
            .order_by(OpmJawabanModel.task_kode)
        ).all()
        return [_to_read(r) for r in rows]

    def get_raw_by_responden(self, responden_id: str) -> dict[str, tuple[int, int, int]]:
        rows = self._s.execute(
            select(
                OpmJawabanModel.task_kode,
                OpmJawabanModel.importance,
                OpmJawabanModel.frequency,
                OpmJawabanModel.criticality,
            ).where(OpmJawabanModel.responden_id == responden_id)
        ).all()
        return {kode: (imp, freq, crit) for kode, imp, freq, crit in rows}

    def bulk_create(
        self, responden_id: str, data: OpmJawabanBulkCreate, valid_task_kodes: set[str]
    ) -> list[OpmJawabanRead]:
        _validate_task_set([j.task_kode for j in data.jawaban], valid_task_kodes)

        already_exists = self._s.scalar(
            select(OpmJawabanModel.id).where(OpmJawabanModel.responden_id == responden_id)
        )
        if already_exists is not None:
            raise ConflictError(
                f"Responden '{responden_id}' sudah memiliki jawaban. "
                "Hapus terlebih dahulu jika ingin mengisi ulang."
            )

        new_records: list[OpmJawabanModel] = []
        for item in data.jawaban:
            rec = OpmJawabanModel(
                id=f"opjw_{uuid.uuid4().hex[:8]}",
                responden_id=responden_id,
                task_kode=item.task_kode,
                importance=item.importance,
                frequency=item.frequency,
                criticality=item.criticality,
                catatan=item.catatan,
            )
            self._s.add(rec)
            new_records.append(rec)
        # SAVEPOINT: unique (responden_id, task_kode) = backstop balapan → ConflictError;
        # transaksi request tetap sehat (rollback hanya ke savepoint).
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(
                f"Responden '{responden_id}' sudah memiliki jawaban. "
                "Hapus terlebih dahulu jika ingin mengisi ulang."
            ) from exc
        return [_to_read(r) for r in new_records]

    def delete_by_responden(self, responden_id: str) -> None:
        rows = self._s.scalars(
            select(OpmJawabanModel).where(OpmJawabanModel.responden_id == responden_id)
        ).all()
        for rec in rows:
            self._s.delete(rec)
        self._s.flush()
