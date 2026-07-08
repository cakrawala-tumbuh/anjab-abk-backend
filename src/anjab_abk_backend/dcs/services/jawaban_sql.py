"""Implementasi `DcsJawabanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryDcsJawabanService` TANPA mengubah kontrak Protocol.

Uniqueness `(responden_id, item_id)` dijaga unique constraint di tabel; `upsert`
melakukan get-or-update per item sehingga draft boleh disimpan berulang kali
sebelum finalisasi. `submit` hanya memvalidasi kelengkapan baris yang sudah ada
di DB (tanpa payload) lalu mengembalikannya.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...errors import ConflictError, ValidationAppError
from ...models import DcsJawabanModel
from ..schemas.jawaban import DcsJawabanRead, DcsJawabanUpsert


def _to_read(rec: DcsJawabanModel) -> DcsJawabanRead:
    return DcsJawabanRead(
        id=rec.id,
        responden_id=rec.responden_id,
        item_id=rec.item_id,
        skor_raw=rec.skor_raw,
    )


class SqlDcsJawabanService:
    """`DcsJawabanService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def list_by_responden(self, responden_id: str) -> list[DcsJawabanRead]:
        rows = self._s.scalars(
            select(DcsJawabanModel)
            .where(DcsJawabanModel.responden_id == responden_id)
            .order_by(DcsJawabanModel.item_id.asc())
        ).all()
        return [_to_read(r) for r in rows]

    def get_raw_by_responden(self, responden_id: str) -> dict[str, int]:
        """Kembalikan mapping {item_id: skor_raw} untuk keperluan analisis."""
        rows = self._s.execute(
            select(DcsJawabanModel.item_id, DcsJawabanModel.skor_raw).where(
                DcsJawabanModel.responden_id == responden_id
            )
        ).all()
        return dict(rows)  # type: ignore[arg-type]

    def upsert(
        self, responden_id: str, data: DcsJawabanUpsert, valid_item_ids: set[str]
    ) -> list[DcsJawabanRead]:
        submitted_ids = {j.item_id for j in data.jawaban}
        unknown = submitted_ids - valid_item_ids
        if unknown:
            raise ConflictError(f"Item tidak dikenal: {', '.join(sorted(unknown))}.")

        results: list[DcsJawabanModel] = []
        for item in data.jawaban:
            existing = self._s.scalar(
                select(DcsJawabanModel).where(
                    DcsJawabanModel.responden_id == responden_id,
                    DcsJawabanModel.item_id == item.item_id,
                )
            )
            if existing is not None:
                existing.skor_raw = item.skor_raw
                results.append(existing)
            else:
                rec = DcsJawabanModel(
                    id=f"djwb_{uuid.uuid4().hex[:8]}",
                    responden_id=responden_id,
                    item_id=item.item_id,
                    skor_raw=item.skor_raw,
                )
                self._s.add(rec)
                results.append(rec)
        self._s.flush()
        return [_to_read(r) for r in results]

    def submit(self, responden_id: str, valid_item_ids: set[str]) -> list[DcsJawabanRead]:
        rows = self._s.scalars(
            select(DcsJawabanModel)
            .where(DcsJawabanModel.responden_id == responden_id)
            .order_by(DcsJawabanModel.item_id.asc())
        ).all()
        existing_ids = {r.item_id for r in rows}
        missing = valid_item_ids - existing_ids
        if missing:
            raise ValidationAppError(
                f"Item berikut belum dijawab: {', '.join(sorted(missing)[:5])}..."
                if len(missing) > 5
                else f"Item berikut belum dijawab: {', '.join(sorted(missing))}."
            )
        return [_to_read(r) for r in rows]

    def delete_by_responden(self, responden_id: str) -> None:
        rows = self._s.scalars(
            select(DcsJawabanModel).where(DcsJawabanModel.responden_id == responden_id)
        ).all()
        for rec in rows:
            self._s.delete(rec)
        self._s.flush()
