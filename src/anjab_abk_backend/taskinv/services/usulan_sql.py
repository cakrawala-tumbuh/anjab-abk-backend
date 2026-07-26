"""Implementasi `TiUsulanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTiUsulanService` TANPA mengubah kontrak Protocol.

`tugas_pokok_id`/`detil_tugas_id` di `TiUsulanTaskModel` sengaja BUKAN `ForeignKey`
(lihat docstring model) — nama induknya diresolusi live lewat `TugasPokokService`/
`DetilTugasService` yang di-inject ke konstruktor, dengan fallback ke id mentah bila
induknya sudah terhapus dari master data (pola sama dengan resolusi `jabatan_label`
di `SqlDcsRespondenService`/`SqlWcpRespondenService`, lihat entri `[2026-07-14]` di
`CLAUDE.md`).
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...errors import NotFoundError
from ...models import TiUsulanTaskModel
from ..schemas.usulan import TiUsulanCreate, TiUsulanRead
from .detil_tugas import DetilTugasService
from .tugas_pokok import TugasPokokService

logger = logging.getLogger(__name__)


class SqlTiUsulanService:
    """`TiUsulanService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(
        self, session: Session, tp_svc: TugasPokokService, dt_svc: DetilTugasService
    ) -> None:
        self._s = session
        self._tp = tp_svc
        self._dt = dt_svc

    def _resolve_nama_tugas_pokok(self, tugas_pokok_id: str) -> str:
        try:
            return self._tp.get(tugas_pokok_id).nama
        except NotFoundError:
            logger.warning(
                "usulan_tugas_pokok_tidak_ditemukan", extra={"tugas_pokok_id": tugas_pokok_id}
            )
            return tugas_pokok_id

    def _resolve_nama_detil_tugas(self, detil_tugas_id: str | None) -> str | None:
        if detil_tugas_id is None:
            return None
        try:
            return self._dt.get(detil_tugas_id).nama
        except NotFoundError:
            logger.warning(
                "usulan_detil_tugas_tidak_ditemukan", extra={"detil_tugas_id": detil_tugas_id}
            )
            return detil_tugas_id

    def _to_read(self, rec: TiUsulanTaskModel) -> TiUsulanRead:
        created = rec.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return TiUsulanRead(
            id=rec.id,
            sesi_id=rec.sesi_id,
            responden_id=rec.responden_id,
            tugas_pokok_id=rec.tugas_pokok_id,
            tugas_pokok=self._resolve_nama_tugas_pokok(rec.tugas_pokok_id),
            detil_tugas_id=rec.detil_tugas_id,
            detil_tugas=self._resolve_nama_detil_tugas(rec.detil_tugas_id),
            uraian=rec.uraian,
            disetujui=rec.disetujui,
            task_kode=rec.task_kode,
            created_at=created,
        )

    def _get_model(self, usulan_id: str) -> TiUsulanTaskModel:
        rec = self._s.get(TiUsulanTaskModel, usulan_id)
        if rec is None:
            raise NotFoundError(f"Usulan '{usulan_id}' tidak ditemukan.")
        return rec

    def create(self, responden_id: str, sesi_id: str, data: TiUsulanCreate) -> TiUsulanRead:
        rec = TiUsulanTaskModel(
            id=f"tius_{uuid.uuid4().hex[:8]}",
            sesi_id=sesi_id,
            responden_id=responden_id,
            tugas_pokok_id=data.tugas_pokok_id,
            detil_tugas_id=data.detil_tugas_id,
            uraian=data.uraian,
        )
        self._s.add(rec)
        self._s.flush()
        return self._to_read(rec)

    def get(self, usulan_id: str) -> TiUsulanRead:
        return self._to_read(self._get_model(usulan_id))

    def list_by_responden(self, responden_id: str) -> list[TiUsulanRead]:
        rows = self._s.scalars(
            select(TiUsulanTaskModel)
            .where(TiUsulanTaskModel.responden_id == responden_id)
            .order_by(TiUsulanTaskModel.created_at)
        ).all()
        return [self._to_read(r) for r in rows]

    def delete(self, usulan_id: str) -> None:
        rec = self._get_model(usulan_id)
        self._s.delete(rec)
        self._s.flush()
