"""SEAM akses data untuk usulan uraian tugas tambahan dari partisipan Tahap 1.

`TiUsulanService` adalah kontrak (Protocol). `InMemoryTiUsulanService` adalah
PLACEHOLDER in-memory. Ganti dengan implementasi PostgreSQL lewat skill
`backend-postgresql-skill` — kontrak tidak berubah (lihat `usulan_sql.py`).

Usulan disimpan hanya sebagai `tugas_pokok_id`/`detil_tugas_id` (bukan snapshot nama);
nama induk (`TiUsulanRead.tugas_pokok`/`.detil_tugas`) diresolusi live lewat
`TugasPokokService`/`DetilTugasService` yang di-inject ke konstruktor — mengikuti pola
resolusi `jabatan_label` di `DcsRespondenService`/`WcpRespondenService` (lihat entri
`[2026-07-14]` di `CLAUDE.md`), termasuk fallback ke id mentah bila induknya sudah
terhapus dari master data.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from ...errors import NotFoundError
from ..schemas.usulan import TiUsulanCreate, TiUsulanRead

if TYPE_CHECKING:
    from .detil_tugas import DetilTugasService
    from .tugas_pokok import TugasPokokService

logger = logging.getLogger(__name__)


@dataclass
class _Record:
    id: str
    sesi_id: str
    responden_id: str
    tugas_pokok_id: str
    detil_tugas_id: str | None
    uraian: str
    disetujui: bool | None
    task_kode: str | None
    created_at: datetime


class TiUsulanService(Protocol):
    """Kontrak operasi terhadap usulan uraian tugas Tahap 1."""

    def create(self, responden_id: str, sesi_id: str, data: TiUsulanCreate) -> TiUsulanRead: ...
    def get(self, usulan_id: str) -> TiUsulanRead: ...
    def list_by_responden(self, responden_id: str) -> list[TiUsulanRead]: ...
    def delete(self, usulan_id: str) -> None: ...


class InMemoryTiUsulanService:
    """Placeholder in-memory thread-safe — BUKAN sumber data nyata."""

    def __init__(
        self,
        tp_svc: TugasPokokService | None = None,
        dt_svc: DetilTugasService | None = None,
    ) -> None:
        self._tp = tp_svc
        self._dt = dt_svc
        self._lock = threading.Lock()
        self._data: dict[str, _Record] = {}

    def _resolve_nama_tugas_pokok(self, tugas_pokok_id: str) -> str:
        if self._tp is None:
            return tugas_pokok_id
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
        if self._dt is None:
            return detil_tugas_id
        try:
            return self._dt.get(detil_tugas_id).nama
        except NotFoundError:
            logger.warning(
                "usulan_detil_tugas_tidak_ditemukan", extra={"detil_tugas_id": detil_tugas_id}
            )
            return detil_tugas_id

    def _to_read(self, rec: _Record) -> TiUsulanRead:
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
            created_at=rec.created_at,
        )

    def create(self, responden_id: str, sesi_id: str, data: TiUsulanCreate) -> TiUsulanRead:
        with self._lock:
            rec = _Record(
                id=f"tius_{uuid.uuid4().hex[:8]}",
                sesi_id=sesi_id,
                responden_id=responden_id,
                tugas_pokok_id=data.tugas_pokok_id,
                detil_tugas_id=data.detil_tugas_id,
                uraian=data.uraian,
                disetujui=None,
                task_kode=None,
                created_at=datetime.now(UTC),
            )
            self._data[rec.id] = rec
            return self._to_read(rec)

    def get(self, usulan_id: str) -> TiUsulanRead:
        with self._lock:
            rec = self._data.get(usulan_id)
        if rec is None:
            raise NotFoundError(f"Usulan '{usulan_id}' tidak ditemukan.")
        return self._to_read(rec)

    def list_by_responden(self, responden_id: str) -> list[TiUsulanRead]:
        with self._lock:
            recs = [r for r in self._data.values() if r.responden_id == responden_id]
        recs.sort(key=lambda r: r.created_at)
        return [self._to_read(r) for r in recs]

    def delete(self, usulan_id: str) -> None:
        with self._lock:
            if usulan_id not in self._data:
                raise NotFoundError(f"Usulan '{usulan_id}' tidak ditemukan.")
            del self._data[usulan_id]
