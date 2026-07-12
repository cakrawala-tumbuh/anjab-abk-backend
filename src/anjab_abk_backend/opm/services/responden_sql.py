"""Implementasi `OpmRespondenService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

`create()` mewajibkan `partisipan_id` yang harus merupakan anggota SME panel
jabatan sesi; duplikasi diperiksa **per sesi** (bukan global — partisipan bisa
menjadi panelis di lebih dari satu jabatan).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import JabatanModel, OpmRespondenModel, PartisipanModel, SMEPanelModel
from ...schemas.common import BulkAssignResult, BulkSkipped
from ..schemas.responden import OpmRespondenCreate, OpmRespondenRead


def _to_read(rec: OpmRespondenModel) -> OpmRespondenRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    submitted = rec.submitted_at
    if submitted is not None and submitted.tzinfo is None:
        submitted = submitted.replace(tzinfo=UTC)
    return OpmRespondenRead(
        id=rec.id,
        sesi_id=rec.sesi_id,
        nama=rec.nama,
        jabatan_label=rec.jabatan_label,
        partisipan_id=rec.partisipan_id,
        sudah_submit=rec.sudah_submit,
        submitted_at=submitted,
        created_at=created,
    )


class SqlOpmRespondenService:
    """`OpmRespondenService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, responden_id: str) -> OpmRespondenModel:
        rec = self._s.get(OpmRespondenModel, responden_id)
        if rec is None:
            raise NotFoundError(f"Responden OPM '{responden_id}' tidak ditemukan.")
        return rec

    def list_by_sesi(self, sesi_id: str) -> list[OpmRespondenRead]:
        rows = self._s.scalars(
            select(OpmRespondenModel)
            .where(OpmRespondenModel.sesi_id == sesi_id)
            .order_by(OpmRespondenModel.created_at)
        ).all()
        return [_to_read(r) for r in rows]

    def list_by_partisipan(self, partisipan_id: str) -> list[OpmRespondenRead]:
        rows = self._s.scalars(
            select(OpmRespondenModel)
            .where(OpmRespondenModel.partisipan_id == partisipan_id)
            .order_by(OpmRespondenModel.created_at)
        ).all()
        return [_to_read(r) for r in rows]

    def count_by_sesi(self, sesi_id: str) -> int:
        return (
            self._s.scalar(
                select(func.count())
                .select_from(OpmRespondenModel)
                .where(OpmRespondenModel.sesi_id == sesi_id)
            )
            or 0
        )

    def get(self, responden_id: str) -> OpmRespondenRead:
        return _to_read(self._get_model(responden_id))

    def create(
        self,
        sesi_id: str,
        data: OpmRespondenCreate,
        max_responden: int,
        jabatan_id: str,
    ) -> OpmRespondenRead:
        current_count = self.count_by_sesi(sesi_id)
        if current_count >= max_responden:
            raise ValidationAppError(
                f"Sesi sudah mencapai batas maksimum {max_responden} responden."
            )

        panel = self._s.scalar(select(SMEPanelModel).where(SMEPanelModel.jabatan_id == jabatan_id))
        if panel is None or data.partisipan_id not in panel.partisipan_ids:
            raise ValidationAppError("Partisipan bukan anggota SME panel jabatan ini.")

        already = self._s.scalar(
            select(OpmRespondenModel.id).where(
                OpmRespondenModel.sesi_id == sesi_id,
                OpmRespondenModel.partisipan_id == data.partisipan_id,
            )
        )
        if already is not None:
            raise ConflictError(
                f"Partisipan '{data.partisipan_id}' sudah terdaftar sebagai responden"
                " OPM di sesi ini."
            )

        rec = OpmRespondenModel(
            id=f"oprs_{uuid.uuid4().hex[:8]}",
            sesi_id=sesi_id,
            nama=data.nama,
            jabatan_label=data.jabatan_label,
            partisipan_id=data.partisipan_id,
            sudah_submit=False,
        )
        self._s.add(rec)
        self._s.flush()
        return _to_read(rec)

    def assign_banyak(
        self,
        sesi_id: str,
        partisipan_ids: list[str],
        *,
        max_responden: int,
        jabatan_id: str,
    ) -> BulkAssignResult[OpmRespondenRead]:
        skipped: list[BulkSkipped] = []
        seen: set[str] = set()
        candidates: list[str] = []
        for partisipan_id in partisipan_ids:
            if partisipan_id in seen:
                skipped.append(BulkSkipped(partisipan_id=partisipan_id, alasan="duplikat_input"))
                continue
            seen.add(partisipan_id)
            candidates.append(partisipan_id)

        panel = self._s.scalar(select(SMEPanelModel).where(SMEPanelModel.jabatan_id == jabatan_id))
        anggota_ids = set(panel.partisipan_ids) if panel is not None else set()

        anggota_valid: list[str] = []
        for partisipan_id in candidates:
            if partisipan_id not in anggota_ids:
                skipped.append(
                    BulkSkipped(partisipan_id=partisipan_id, alasan="bukan_anggota_sme_panel")
                )
                continue
            anggota_valid.append(partisipan_id)

        existing_ids: set[str] = set()
        if anggota_valid:
            existing_ids = set(
                self._s.scalars(
                    select(OpmRespondenModel.partisipan_id).where(
                        OpmRespondenModel.sesi_id == sesi_id,
                        OpmRespondenModel.partisipan_id.in_(anggota_valid),
                    )
                ).all()
            )

        current_count = self.count_by_sesi(sesi_id)
        jabatan = self._s.get(JabatanModel, jabatan_id)
        par_map: dict[str, PartisipanModel] = {}
        to_create = [pid for pid in anggota_valid if pid not in existing_ids]
        if to_create:
            par_rows = self._s.scalars(
                select(PartisipanModel).where(PartisipanModel.id.in_(to_create))
            ).all()
            par_map = {p.id: p for p in par_rows}

        created: list[OpmRespondenRead] = []
        for partisipan_id in anggota_valid:
            if partisipan_id in existing_ids:
                skipped.append(BulkSkipped(partisipan_id=partisipan_id, alasan="sudah_terdaftar"))
                continue
            if current_count >= max_responden:
                skipped.append(BulkSkipped(partisipan_id=partisipan_id, alasan="kapasitas_penuh"))
                continue
            par = par_map.get(partisipan_id)
            rec = OpmRespondenModel(
                id=f"oprs_{uuid.uuid4().hex[:8]}",
                sesi_id=sesi_id,
                nama=par.nama if par else None,
                jabatan_label=jabatan.nama if jabatan else "",
                partisipan_id=partisipan_id,
                sudah_submit=False,
            )
            self._s.add(rec)
            self._s.flush()
            current_count += 1
            created.append(_to_read(rec))

        return BulkAssignResult(created=created, skipped=skipped)

    def mark_submitted(self, responden_id: str) -> OpmRespondenRead:
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
