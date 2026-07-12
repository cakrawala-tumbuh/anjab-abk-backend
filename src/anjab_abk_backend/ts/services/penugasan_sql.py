"""Implementasi `TsPenugasanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTsPenugasanService` TANPA mengubah kontrak Protocol.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError
from ...models import TsPenugasanModel
from ...schemas.common import BulkAssignResult, BulkSkipped
from ..schemas.penugasan import TsPenugasanCreate, TsPenugasanRead, TsPenugasanUpdate


def _to_read(rec: TsPenugasanModel) -> TsPenugasanRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return TsPenugasanRead(
        id=rec.id,
        partisipan_id=rec.partisipan_id,
        aktif=rec.aktif,
        catatan=rec.catatan,
        created_at=created,
    )


class SqlTsPenugasanService:
    """`TsPenugasanService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, penugasan_id: str) -> TsPenugasanModel:
        rec = self._s.get(TsPenugasanModel, penugasan_id)
        if rec is None:
            raise NotFoundError(f"Penugasan Time Study '{penugasan_id}' tidak ditemukan.")
        return rec

    def list(self, *, limit: int, offset: int) -> tuple[list[TsPenugasanRead], int]:
        total = self._s.scalar(select(func.count()).select_from(TsPenugasanModel)) or 0
        rows = self._s.scalars(
            select(TsPenugasanModel)
            .order_by(TsPenugasanModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def get(self, penugasan_id: str) -> TsPenugasanRead:
        return _to_read(self._get_model(penugasan_id))

    def get_by_partisipan(self, partisipan_id: str) -> TsPenugasanRead | None:
        rec = self._s.scalar(
            select(TsPenugasanModel).where(TsPenugasanModel.partisipan_id == partisipan_id)
        )
        return _to_read(rec) if rec is not None else None

    def create(self, data: TsPenugasanCreate) -> TsPenugasanRead:
        already = self._s.scalar(
            select(TsPenugasanModel.id).where(TsPenugasanModel.partisipan_id == data.partisipan_id)
        )
        if already is not None:
            raise ConflictError(
                f"Partisipan '{data.partisipan_id}' sudah memiliki penugasan Time Study."
            )
        rec = TsPenugasanModel(
            id=f"tpn_{uuid.uuid4().hex[:8]}",
            partisipan_id=data.partisipan_id,
            aktif=data.aktif,
            catatan=data.catatan,
        )
        self._s.add(rec)
        self._s.flush()
        return _to_read(rec)

    def create_banyak(
        self, partisipan_ids: list[str], *, aktif: bool, catatan: str | None
    ) -> BulkAssignResult[TsPenugasanRead]:
        """Catatan implementasi: `sudah_terdaftar` dideteksi via pre-check SELECT
        (bukan `begin_nested()` per baris + tangkap `IntegrityError`) — pola savepoint
        per-item terbukti TIDAK aman dipakai berulang dalam satu loop: setelah SATU
        `IntegrityError` tertangkap, `Session` induk masuk keadaan yang mewajibkan
        `rollback()` penuh sebelum dipakai lagi, dan `rollback()` itu ikut membuang
        baris lain yang sudah berhasil di-flush pada iterasi sebelumnya (belum
        `commit`). Pre-check menghindari jebakan ini sekaligus tetap idempoten;
        backstop `IntegrityError` di flush akhir hanya untuk race jarang (dua
        request bersamaan menugaskan partisipan yang sama).
        """
        skipped: list[BulkSkipped] = []
        seen: set[str] = set()
        candidates: list[str] = []
        for partisipan_id in partisipan_ids:
            if partisipan_id in seen:
                skipped.append(BulkSkipped(partisipan_id=partisipan_id, alasan="duplikat_input"))
                continue
            seen.add(partisipan_id)
            candidates.append(partisipan_id)

        existing_ids: set[str] = set()
        if candidates:
            existing_ids = set(
                self._s.scalars(
                    select(TsPenugasanModel.partisipan_id).where(
                        TsPenugasanModel.partisipan_id.in_(candidates)
                    )
                ).all()
            )

        recs: list[TsPenugasanModel] = []
        for partisipan_id in candidates:
            if partisipan_id in existing_ids:
                skipped.append(BulkSkipped(partisipan_id=partisipan_id, alasan="sudah_terdaftar"))
                continue
            rec = TsPenugasanModel(
                id=f"tpn_{uuid.uuid4().hex[:8]}",
                partisipan_id=partisipan_id,
                aktif=aktif,
                catatan=catatan,
            )
            self._s.add(rec)
            recs.append(rec)

        if recs:
            try:
                with self._s.begin_nested():
                    self._s.flush()
            except IntegrityError as exc:
                raise ConflictError(
                    "Salah satu partisipan sudah memiliki penugasan Time Study."
                ) from exc

        return BulkAssignResult(
            created=[_to_read(r) for r in recs],
            skipped=skipped,
        )

    def update(self, penugasan_id: str, data: TsPenugasanUpdate) -> TsPenugasanRead:
        rec = self._get_model(penugasan_id)
        changes = data.model_dump(exclude_unset=True)
        for key, value in changes.items():
            setattr(rec, key, value)
        self._s.flush()
        return _to_read(rec)

    def delete(self, penugasan_id: str) -> None:
        rec = self._get_model(penugasan_id)
        self._s.delete(rec)
        self._s.flush()
