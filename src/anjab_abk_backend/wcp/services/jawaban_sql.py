"""Implementasi `WcpJawabanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryWcpJawabanService` TANPA mengubah kontrak Protocol.

Uniqueness `(responden_id, item_id)` dijaga oleh `UniqueConstraint` di model;
`upsert` melakukan get-or-update per item sehingga draft boleh disimpan berulang
kali sebelum finalisasi. `submit` hanya memvalidasi kelengkapan baris yang sudah
ada di DB (tanpa payload) lalu mengembalikannya. Sejak instrumen menjadi singleton
(bukan lagi per kumpulan responden terpisah), gerbang "hanya boleh diubah saat
OPEN" dicek langsung di sini terhadap baris tunggal `wcp_instrumen` (lewat objek
`Session` yang sama) alih-alih lewat status kumpulan responden seperti sebelumnya.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...errors import ConflictError, ValidationAppError
from ...models import WcpInstrumenModel, WcpJawabanModel
from ..schemas.jawaban import WcpJawabanRead, WcpJawabanUpsert
from .instrumen import INSTRUMEN_ID


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

    def _require_instrumen_open(self) -> None:
        instrumen = self._s.get(WcpInstrumenModel, INSTRUMEN_ID)
        status = instrumen.status if instrumen is not None else "TIDAK ADA"
        if status != "OPEN":
            raise ValidationAppError(
                f"Jawaban hanya dapat diubah saat instrumen WCP berstatus OPEN"
                f" (saat ini: {status})."
            )

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

    def upsert(
        self, responden_id: str, data: WcpJawabanUpsert, valid_item_ids: set[str]
    ) -> list[WcpJawabanRead]:
        self._require_instrumen_open()
        submitted_ids = {j.item_id for j in data.jawaban}
        unknown = submitted_ids - valid_item_ids
        if unknown:
            raise ConflictError(f"Item tidak dikenal: {', '.join(sorted(unknown))}.")

        results: list[WcpJawabanModel] = []
        for item in data.jawaban:
            existing = self._s.scalar(
                select(WcpJawabanModel).where(
                    WcpJawabanModel.responden_id == responden_id,
                    WcpJawabanModel.item_id == item.item_id,
                )
            )
            if existing is not None:
                existing.skor_raw = item.skor_raw
                results.append(existing)
            else:
                rec = WcpJawabanModel(
                    id=f"wjwb_{uuid.uuid4().hex[:8]}",
                    responden_id=responden_id,
                    item_id=item.item_id,
                    skor_raw=item.skor_raw,
                )
                self._s.add(rec)
                results.append(rec)
        self._s.flush()
        return [_to_read(r) for r in results]

    def submit(self, responden_id: str, valid_item_ids: set[str]) -> list[WcpJawabanRead]:
        self._require_instrumen_open()
        rows = self._s.scalars(
            select(WcpJawabanModel)
            .where(WcpJawabanModel.responden_id == responden_id)
            .order_by(WcpJawabanModel.item_id)
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
            select(WcpJawabanModel).where(WcpJawabanModel.responden_id == responden_id)
        ).all()
        for rec in rows:
            self._s.delete(rec)
        self._s.flush()
