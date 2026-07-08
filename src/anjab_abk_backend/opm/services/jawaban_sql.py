"""Implementasi `OpmJawabanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

Uniqueness `(responden_id, task_kode)` dijaga oleh `UniqueConstraint` di model;
`upsert` melakukan get-or-update per item sehingga draft boleh disimpan berulang
kali sebelum finalisasi. `submit` hanya memvalidasi kelengkapan baris yang sudah
ada di DB (tanpa payload) lalu mengembalikannya.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import OpmJawabanModel
from ..schemas.jawaban import OpmJawabanRead, OpmJawabanUpsert
from .jawaban import _validate_task_set, _validate_task_subset


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

    def upsert(
        self, responden_id: str, data: OpmJawabanUpsert, valid_task_kodes: set[str]
    ) -> list[OpmJawabanRead]:
        _validate_task_subset([j.task_kode for j in data.jawaban], valid_task_kodes)

        results: list[OpmJawabanModel] = []
        for item in data.jawaban:
            existing = self._s.scalar(
                select(OpmJawabanModel).where(
                    OpmJawabanModel.responden_id == responden_id,
                    OpmJawabanModel.task_kode == item.task_kode,
                )
            )
            if existing is not None:
                existing.importance = item.importance
                existing.frequency = item.frequency
                existing.criticality = item.criticality
                existing.catatan = item.catatan
                results.append(existing)
            else:
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
                results.append(rec)
        self._s.flush()
        return [_to_read(r) for r in results]

    def submit(self, responden_id: str, valid_task_kodes: set[str]) -> list[OpmJawabanRead]:
        rows = self._s.scalars(
            select(OpmJawabanModel)
            .where(OpmJawabanModel.responden_id == responden_id)
            .order_by(OpmJawabanModel.task_kode)
        ).all()
        _validate_task_set([r.task_kode for r in rows], valid_task_kodes)
        return [_to_read(r) for r in rows]

    def delete_by_responden(self, responden_id: str) -> None:
        rows = self._s.scalars(
            select(OpmJawabanModel).where(OpmJawabanModel.responden_id == responden_id)
        ).all()
        for rec in rows:
            self._s.delete(rec)
        self._s.flush()
