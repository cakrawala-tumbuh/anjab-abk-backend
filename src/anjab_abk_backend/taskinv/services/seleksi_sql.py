"""Implementasi `TiSeleksiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTiSeleksiService` TANPA mengubah kontrak Protocol.

Disimpan 1 baris per (responden, task_kode) di `ti_seleksi` agar mudah menghitung
union antar responden dan jumlah relevansi per task.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import ConflictError, ValidationAppError
from ...models import TiSeleksiModel
from ..schemas.seleksi import TiSeleksiRead


class SqlTiSeleksiService:
    """`TiSeleksiService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def submit(
        self, responden_id: str, sesi_id: str, kodes: list[str], valid_kodes: set[str]
    ) -> TiSeleksiRead:
        unik = sorted(set(kodes))
        unknown = set(unik) - valid_kodes
        if unknown:
            raise ValidationAppError(
                f"Kode task tidak valid untuk kombinasi sesi: {', '.join(sorted(unknown)[:5])}"
                + ("..." if len(unknown) > 5 else ".")
            )
        already = self._s.scalar(
            select(TiSeleksiModel.id).where(TiSeleksiModel.responden_id == responden_id)
        )
        if already is not None:
            raise ConflictError(f"Responden '{responden_id}' sudah submit seleksi Tahap 1.")
        now = datetime.now(UTC)
        for kode in unik:
            self._s.add(
                TiSeleksiModel(
                    id=f"tsel_{uuid.uuid4().hex[:8]}",
                    responden_id=responden_id,
                    sesi_id=sesi_id,
                    task_kode=kode,
                    created_at=now,
                )
            )
        self._s.flush()
        return TiSeleksiRead(
            responden_id=responden_id, sesi_id=sesi_id, task_kode=unik, submitted_at=now
        )

    def get_by_responden(self, responden_id: str) -> TiSeleksiRead | None:
        rows = self._s.scalars(
            select(TiSeleksiModel).where(TiSeleksiModel.responden_id == responden_id)
        ).all()
        if not rows:
            return None
        created = min(r.created_at for r in rows)
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        return TiSeleksiRead(
            responden_id=responden_id,
            sesi_id=rows[0].sesi_id,
            task_kode=sorted(r.task_kode for r in rows),
            submitted_at=created,
        )

    def union_terpilih(self, sesi_id: str) -> list[str]:
        rows = self._s.scalars(
            select(TiSeleksiModel.task_kode).where(TiSeleksiModel.sesi_id == sesi_id).distinct()
        ).all()
        return sorted(set(rows))

    def unanimous_terpilih(self, sesi_id: str, total_submitted: int) -> list[str]:
        """Task yang dipilih oleh SEMUA responden yang sudah submit Tahap 1."""
        counts = self.count_relevan_per_task(sesi_id)
        if total_submitted == 0:
            return []
        return sorted(kode for kode, n in counts.items() if n >= total_submitted)

    def partial_terpilih(self, sesi_id: str, total_submitted: int) -> list[str]:
        """Task yang dipilih oleh SEBAGIAN (bukan semua) responden — butuh review koordinator."""
        counts = self.count_relevan_per_task(sesi_id)
        if total_submitted == 0:
            return []
        return sorted(kode for kode, n in counts.items() if 0 < n < total_submitted)

    def count_relevan_per_task(self, sesi_id: str) -> dict[str, int]:
        rows = self._s.execute(
            select(TiSeleksiModel.task_kode, func.count())
            .where(TiSeleksiModel.sesi_id == sesi_id)
            .group_by(TiSeleksiModel.task_kode)
        ).all()
        return {kode: int(n) for kode, n in rows}

    def delete_by_responden(self, responden_id: str) -> None:
        rows = self._s.scalars(
            select(TiSeleksiModel).where(TiSeleksiModel.responden_id == responden_id)
        ).all()
        for rec in rows:
            self._s.delete(rec)
        self._s.flush()
