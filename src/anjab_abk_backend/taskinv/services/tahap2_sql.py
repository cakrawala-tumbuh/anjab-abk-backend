"""Implementasi `TiTahap2Service` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTiTahap2Service` TANPA mengubah kontrak Protocol.

Keputusan koordinator unik per (sesi_id, task_kode); resubmit melakukan
upsert/replace (memperbarui `disetujui` & `submitted_at` baris yang ada).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...errors import ValidationAppError
from ...models import TiTahap2Model
from ..schemas.tahap2 import TiTahap2KeputusanItem, TiTahap2ReviewRead, TiTahap2TaskRead


class SqlTiTahap2Service:
    """`TiTahap2Service` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def get_review(
        self, sesi_id: str, partial_kodes: list[str], counts: dict[str, int], n_total: int
    ) -> TiTahap2ReviewRead:
        rows = self._s.scalars(select(TiTahap2Model).where(TiTahap2Model.sesi_id == sesi_id)).all()
        existing: dict[str, TiTahap2Model] = {r.task_kode: r for r in rows}
        tasks: list[TiTahap2TaskRead] = []
        last_at: datetime | None = None
        for kode in partial_kodes:
            kep = existing.get(kode)
            disetujui = kep.disetujui if kep else None
            if kep is not None:
                kep_at = kep.submitted_at
                if kep_at.tzinfo is None:
                    kep_at = kep_at.replace(tzinfo=UTC)
                if last_at is None or kep_at > last_at:
                    last_at = kep_at
            tasks.append(
                TiTahap2TaskRead(
                    task_kode=kode,
                    n_relevan=counts.get(kode, 0),
                    n_total=n_total,
                    disetujui=disetujui,
                )
            )
        belum = sum(1 for t in tasks if t.disetujui is None)
        return TiTahap2ReviewRead(
            sesi_id=sesi_id,
            tasks=tasks,
            jumlah_belum_diputuskan=belum,
            submitted_at=last_at,
        )

    def submit_keputusan(
        self, sesi_id: str, keputusan: list[TiTahap2KeputusanItem], valid_kodes: set[str]
    ) -> TiTahap2ReviewRead:
        unknown = {k.task_kode for k in keputusan} - valid_kodes
        if unknown:
            raise ValidationAppError(
                f"Kode task tidak valid untuk sesi ini: {', '.join(sorted(unknown)[:5])}"
                + ("..." if len(unknown) > 5 else ".")
            )
        now = datetime.now(UTC)
        submitted_kodes = {k.task_kode for k in keputusan}
        existing_rows = self._s.scalars(
            select(TiTahap2Model).where(TiTahap2Model.sesi_id == sesi_id)
        ).all()
        by_kode: dict[str, TiTahap2Model] = {r.task_kode: r for r in existing_rows}
        for item in keputusan:
            existing = by_kode.get(item.task_kode)
            if existing is not None:
                existing.disetujui = item.disetujui
                existing.submitted_at = now
            else:
                rec = TiTahap2Model(
                    id=f"tt2k_{uuid.uuid4().hex[:8]}",
                    sesi_id=sesi_id,
                    task_kode=item.task_kode,
                    disetujui=item.disetujui,
                    submitted_at=now,
                )
                self._s.add(rec)
                by_kode[item.task_kode] = rec
        self._s.flush()
        tasks: list[TiTahap2TaskRead] = []
        for kode in sorted(submitted_kodes):
            kep = by_kode.get(kode)
            tasks.append(
                TiTahap2TaskRead(
                    task_kode=kode,
                    n_relevan=0,
                    n_total=0,
                    disetujui=kep.disetujui if kep else None,
                )
            )
        belum = sum(1 for t in tasks if t.disetujui is None)
        return TiTahap2ReviewRead(
            sesi_id=sesi_id,
            tasks=tasks,
            jumlah_belum_diputuskan=belum,
            submitted_at=now,
        )

    def get_approved_kodes(self, sesi_id: str) -> list[str]:
        """Kode task yang disetujui koordinator (untuk digabung dengan unanimous)."""
        rows = self._s.scalars(
            select(TiTahap2Model.task_kode).where(
                TiTahap2Model.sesi_id == sesi_id, TiTahap2Model.disetujui.is_(True)
            )
        ).all()
        return sorted(rows)

    def delete_by_sesi(self, sesi_id: str) -> None:
        rows = self._s.scalars(select(TiTahap2Model).where(TiTahap2Model.sesi_id == sesi_id)).all()
        for rec in rows:
            self._s.delete(rec)
        self._s.flush()
