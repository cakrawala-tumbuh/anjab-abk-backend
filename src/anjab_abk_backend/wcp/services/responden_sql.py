"""Implementasi `WcpRespondenService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryWcpRespondenService` TANPA mengubah kontrak Protocol.

`partisipan_id` unik lintas SELURUH responden (constraint DB `uq_wcp_responden_
partisipan_id`); pre-cek dilakukan untuk pesan error ramah, dengan backstop
`IntegrityError` → `ConflictError` (pola `anjab/services/sme_panel_sql.py`).

`create_banyak` bersifat idempoten (skip-on-conflict), BUKAN atomik — meniru pola
`SqlTsPenugasanService.create_banyak`/`SqlOpmRespondenService.assign_banyak`: tiap
`partisipan_id` yang gagal (duplikat di input atau sudah terdaftar) dikumpulkan ke
`BulkAssignResult.skipped`, sisanya tetap dibuat dalam satu batch.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...anjab.services.jabatan import JabatanService
from ...core.services.partisipan import PartisipanService
from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import WcpInstrumenModel, WcpRespondenModel
from ...schemas.common import BulkAssignResult, BulkSkipped
from ..schemas.responden import WcpRespondenRead

# Sumber tunggal id singleton instrumen.
from .instrumen import INSTRUMEN_ID

logger = logging.getLogger(__name__)


def _to_read(rec: WcpRespondenModel) -> WcpRespondenRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    submitted = rec.submitted_at
    if submitted is not None and submitted.tzinfo is None:
        submitted = submitted.replace(tzinfo=UTC)
    return WcpRespondenRead(
        id=rec.id,
        nama=rec.nama,
        jabatan_label=rec.jabatan_label,
        partisipan_id=rec.partisipan_id,
        sudah_submit=rec.sudah_submit,
        submitted_at=submitted,
        created_at=created,
    )


class SqlWcpRespondenService:
    """`WcpRespondenService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(
        self,
        session: Session,
        partisipan_service: PartisipanService,
        jabatan_service: JabatanService,
    ) -> None:
        self._s = session
        self._par = partisipan_service
        self._jab = jabatan_service

    def _get_model(self, responden_id: str) -> WcpRespondenModel:
        rec = self._s.get(WcpRespondenModel, responden_id)
        if rec is None:
            raise NotFoundError(f"Responden WCP '{responden_id}' tidak ditemukan.")
        return rec

    def _flush_checked(self, *, on_conflict: str) -> None:
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(on_conflict) from exc

    def _require_instrumen_open(self) -> None:
        instrumen = self._s.get(WcpInstrumenModel, INSTRUMEN_ID)
        status = instrumen.status if instrumen is not None else "TIDAK ADA"
        if status != "OPEN":
            raise ConflictError(
                f"Responden hanya dapat ditambahkan saat instrumen WCP berstatus OPEN"
                f" (saat ini: {status})."
            )

    def list_all(
        self, *, limit: int | None = None, offset: int = 0
    ) -> tuple[list[WcpRespondenRead], int]:
        total = self._s.scalar(select(func.count()).select_from(WcpRespondenModel)) or 0
        stmt = select(WcpRespondenModel).order_by(WcpRespondenModel.created_at.asc())
        if limit is not None:
            stmt = stmt.limit(limit).offset(offset)
        elif offset:
            stmt = stmt.offset(offset)
        rows = self._s.scalars(stmt).all()
        return [_to_read(r) for r in rows], total

    def list_by_partisipan(self, partisipan_id: str) -> list[WcpRespondenRead]:
        rows = self._s.scalars(
            select(WcpRespondenModel)
            .where(WcpRespondenModel.partisipan_id == partisipan_id)
            .order_by(WcpRespondenModel.created_at.asc())
        ).all()
        return [_to_read(r) for r in rows]

    def get(self, responden_id: str) -> WcpRespondenRead:
        return _to_read(self._get_model(responden_id))

    def _insert(
        self, partisipan_id: str, nama: str | None, jabatan_label: str
    ) -> WcpRespondenModel:
        already = self._s.scalar(
            select(WcpRespondenModel.id).where(WcpRespondenModel.partisipan_id == partisipan_id)
        )
        if already is not None:
            raise ConflictError(
                f"Partisipan '{partisipan_id}' sudah terdaftar sebagai responden WCP."
            )
        rec = WcpRespondenModel(
            id=f"wrsp_{uuid.uuid4().hex[:8]}",
            nama=nama,
            jabatan_label=jabatan_label,
            partisipan_id=partisipan_id,
            sudah_submit=False,
        )
        self._s.add(rec)
        return rec

    def create(self, partisipan_id: str, nama: str | None, jabatan_label: str) -> WcpRespondenRead:
        self._require_instrumen_open()
        rec = self._insert(partisipan_id, nama, jabatan_label)
        self._flush_checked(
            on_conflict=f"Partisipan '{partisipan_id}' sudah terdaftar sebagai responden WCP."
        )
        return _to_read(rec)

    def create_banyak(self, partisipan_ids: list[str]) -> BulkAssignResult[WcpRespondenRead]:
        """Idempoten (skip-on-conflict), BUKAN atomik.

        Urutan pengecekan: dedup input (`duplikat_input`) → sudah terdaftar
        (`sudah_terdaftar`, dicek via pre-check SELECT — bukan `begin_nested()`
        per baris, lihat catatan di `SqlTsPenugasanService.create_banyak`). Tidak
        ada konsep keanggotaan panel/kapasitas untuk WCP (beda dari OPM/TI).
        """
        self._require_instrumen_open()

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
                    select(WcpRespondenModel.partisipan_id).where(
                        WcpRespondenModel.partisipan_id.in_(candidates)
                    )
                ).all()
            )

        recs: list[WcpRespondenModel] = []
        for partisipan_id in candidates:
            if partisipan_id in existing_ids:
                skipped.append(BulkSkipped(partisipan_id=partisipan_id, alasan="sudah_terdaftar"))
                continue
            partisipan = self._par.get(partisipan_id)
            try:
                jabatan_label = self._jab.get(partisipan.jabatan_utama_id).nama
            except NotFoundError:
                jabatan_label = partisipan.jabatan_utama_id
                logger.warning(
                    "Jabatan '%s' tidak ditemukan untuk partisipan '%s' — jabatan_label WCP"
                    " fallback ke ID mentah.",
                    partisipan.jabatan_utama_id,
                    partisipan_id,
                )
            rec = WcpRespondenModel(
                id=f"wrsp_{uuid.uuid4().hex[:8]}",
                nama=partisipan.nama,
                jabatan_label=jabatan_label,
                partisipan_id=partisipan_id,
                sudah_submit=False,
            )
            self._s.add(rec)
            recs.append(rec)

        if recs:
            try:
                with self._s.begin_nested():
                    self._s.flush()
            except IntegrityError as exc:
                raise ConflictError(
                    "Salah satu partisipan sudah terdaftar sebagai responden WCP."
                ) from exc

        return BulkAssignResult(created=[_to_read(r) for r in recs], skipped=skipped)

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
