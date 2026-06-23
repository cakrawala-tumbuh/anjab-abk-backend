"""Implementasi `DcsJawabanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryDcsJawabanService` TANPA mengubah kontrak Protocol.

Uniqueness `(responden_id, item_id)` dijaga unique constraint di tabel; flush
dalam SAVEPOINT memetakan `IntegrityError` → `ConflictError` (409) tanpa merusak
transaksi request.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError
from ...models import DcsJawabanModel
from ..schemas.jawaban import DcsJawabanBulkCreate, DcsJawabanRead


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

    def bulk_create(
        self, responden_id: str, data: DcsJawabanBulkCreate, valid_item_ids: set[str]
    ) -> list[DcsJawabanRead]:
        submitted_ids = {j.item_id for j in data.jawaban}
        missing = valid_item_ids - submitted_ids
        if missing:
            raise ConflictError(
                f"Item berikut belum dijawab: {', '.join(sorted(missing)[:5])}..."
                if len(missing) > 5
                else f"Item berikut belum dijawab: {', '.join(sorted(missing))}."
            )
        unknown = submitted_ids - valid_item_ids
        if unknown:
            raise ConflictError(f"Item tidak dikenal: {', '.join(sorted(unknown))}.")

        already_exists = self._s.scalar(
            select(DcsJawabanModel.id).where(DcsJawabanModel.responden_id == responden_id)
        )
        if already_exists is not None:
            raise ConflictError(
                f"Responden '{responden_id}' sudah memiliki jawaban. "
                "Hapus terlebih dahulu jika ingin mengisi ulang."
            )

        new_records: list[DcsJawabanModel] = []
        for item in data.jawaban:
            rec = DcsJawabanModel(
                id=f"djwb_{uuid.uuid4().hex[:8]}",
                responden_id=responden_id,
                item_id=item.item_id,
                skor_raw=item.skor_raw,
            )
            self._s.add(rec)
            new_records.append(rec)
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
            select(DcsJawabanModel).where(DcsJawabanModel.responden_id == responden_id)
        ).all()
        for rec in rows:
            self._s.delete(rec)
        self._s.flush()
