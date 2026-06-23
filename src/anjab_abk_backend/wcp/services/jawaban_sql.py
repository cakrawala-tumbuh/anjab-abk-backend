"""Implementasi `WcpJawabanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryWcpJawabanService` TANPA mengubah kontrak Protocol — signature
method identik, sehingga router, skema, error envelope, dan test kontrak HTTP
tidak ikut berubah.

Uniqueness `(responden_id, item_id)` dijaga oleh `UniqueConstraint` di model;
flush dalam SAVEPOINT memetakan `IntegrityError` (balapan) → `ConflictError`
sehingga transaksi request tetap sehat.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError
from ...models import WcpJawabanModel
from ..schemas.jawaban import WcpJawabanBulkCreate, WcpJawabanRead


def _to_read(rec: WcpJawabanModel) -> WcpJawabanRead:
    return WcpJawabanRead(
        id=rec.id,
        responden_id=rec.responden_id,
        item_id=rec.item_id,
        skor_raw=rec.skor_raw,
    )


class SqlWcpJawabanService:
    """`WcpJawabanService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def list_by_responden(self, responden_id: str) -> list[WcpJawabanRead]:
        rows = self._s.scalars(
            select(WcpJawabanModel)
            .where(WcpJawabanModel.responden_id == responden_id)
            .order_by(WcpJawabanModel.item_id)
        ).all()
        return [_to_read(r) for r in rows]

    def get_raw_by_responden(self, responden_id: str) -> dict[str, int]:
        """Kembalikan mapping {item_id: skor_raw} untuk keperluan analisis."""
        rows = self._s.execute(
            select(WcpJawabanModel.item_id, WcpJawabanModel.skor_raw).where(
                WcpJawabanModel.responden_id == responden_id
            )
        ).all()
        return dict(rows)

    def bulk_create(
        self, responden_id: str, data: WcpJawabanBulkCreate, valid_item_ids: set[str]
    ) -> list[WcpJawabanRead]:
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
            select(WcpJawabanModel.id).where(WcpJawabanModel.responden_id == responden_id)
        )
        if already_exists is not None:
            raise ConflictError(
                f"Responden '{responden_id}' sudah memiliki jawaban. "
                "Hapus terlebih dahulu jika ingin mengisi ulang."
            )

        new_records: list[WcpJawabanModel] = []
        for item in data.jawaban:
            rec = WcpJawabanModel(
                id=f"wjwb_{uuid.uuid4().hex[:8]}",
                responden_id=responden_id,
                item_id=item.item_id,
                skor_raw=item.skor_raw,
            )
            self._s.add(rec)
            new_records.append(rec)
        # SAVEPOINT: unique (responden_id, item_id) = backstop balapan → ConflictError;
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
            select(WcpJawabanModel).where(WcpJawabanModel.responden_id == responden_id)
        ).all()
        for rec in rows:
            self._s.delete(rec)
        self._s.flush()
