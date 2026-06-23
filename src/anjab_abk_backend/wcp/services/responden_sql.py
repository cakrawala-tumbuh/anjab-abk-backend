"""Implementasi `WcpRespondenService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryWcpRespondenService` TANPA mengubah kontrak Protocol — signature
method identik, sehingga router, skema, error envelope, dan test kontrak HTTP
tidak ikut berubah.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import WcpRespondenModel
from ..schemas.responden import WcpRespondenCreate, WcpRespondenRead


def _to_read(rec: WcpRespondenModel) -> WcpRespondenRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    submitted = rec.submitted_at
    if submitted is not None and submitted.tzinfo is None:
        submitted = submitted.replace(tzinfo=UTC)
    return WcpRespondenRead(
        id=rec.id,
        sesi_id=rec.sesi_id,
        nama=rec.nama,
        jabatan_label=rec.jabatan_label,
        partisipan_id=rec.partisipan_id,
        sudah_submit=rec.sudah_submit,
        submitted_at=submitted,
        created_at=created,
    )


class SqlWcpRespondenService:
    """`WcpRespondenService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, responden_id: str) -> WcpRespondenModel:
        rec = self._s.get(WcpRespondenModel, responden_id)
        if rec is None:
            raise NotFoundError(f"Responden WCP '{responden_id}' tidak ditemukan.")
        return rec

    def list_by_sesi(self, sesi_id: str) -> list[WcpRespondenRead]:
        rows = self._s.scalars(
            select(WcpRespondenModel)
            .where(WcpRespondenModel.sesi_id == sesi_id)
            .order_by(WcpRespondenModel.created_at)
        ).all()
        return [_to_read(r) for r in rows]

    def list_by_partisipan(self, partisipan_id: str) -> list[WcpRespondenRead]:
        rows = self._s.scalars(
            select(WcpRespondenModel)
            .where(WcpRespondenModel.partisipan_id == partisipan_id)
            .order_by(WcpRespondenModel.created_at)
        ).all()
        return [_to_read(r) for r in rows]

    def count_by_sesi(self, sesi_id: str) -> int:
        return (
            self._s.scalar(
                select(func.count())
                .select_from(WcpRespondenModel)
                .where(WcpRespondenModel.sesi_id == sesi_id)
            )
            or 0
        )

    def get(self, responden_id: str) -> WcpRespondenRead:
        return _to_read(self._get_model(responden_id))

    def create(
        self, sesi_id: str, data: WcpRespondenCreate, max_responden: int
    ) -> WcpRespondenRead:
        current_count = self.count_by_sesi(sesi_id)
        if current_count >= max_responden:
            raise ValidationAppError(
                f"Sesi sudah mencapai batas maksimum {max_responden} responden."
            )
        if data.partisipan_id is not None:
            already = self._s.scalar(
                select(WcpRespondenModel.id).where(
                    WcpRespondenModel.partisipan_id == data.partisipan_id
                )
            )
            if already is not None:
                raise ConflictError(
                    f"Partisipan '{data.partisipan_id}' sudah terdaftar sebagai responden WCP."
                )
        rec = WcpRespondenModel(
            id=f"wrsp_{uuid.uuid4().hex[:8]}",
            sesi_id=sesi_id,
            nama=data.nama,
            jabatan_label=data.jabatan_label,
            partisipan_id=data.partisipan_id,
            sudah_submit=False,
        )
        self._s.add(rec)
        self._s.flush()
        return _to_read(rec)

    def mark_submitted(self, responden_id: str) -> WcpRespondenRead:
        rec = self._get_model(responden_id)
        if rec.sudah_submit:
            raise ValidationAppError("Responden ini sudah pernah mengirimkan jawaban.")
        rec.sudah_submit = True
        rec.submitted_at = datetime.now(UTC)
        self._s.flush()
        return _to_read(rec)

    def delete(self, responden_id: str) -> None:
        rec = self._get_model(responden_id)
        if rec.sudah_submit:
            raise ValidationAppError("Responden yang sudah submit tidak dapat dihapus.")
        self._s.delete(rec)
        self._s.flush()
