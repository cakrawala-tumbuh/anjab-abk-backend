"""Implementasi `TiDetailService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTiDetailService` TANPA mengubah kontrak Protocol.

Satu baris per (responden, task_kode) di `ti_detail`. Submit divalidasi:
duplikat task_kode dalam payload → 422; task_kode di luar himpunan terpilih → 422;
responden yang sudah submit → 409.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import ConflictError, ValidationAppError
from ...models import TiDetailModel
from ..schemas.detail import TiDetailRead, TiDetailSubmit


def _to_read(rec: TiDetailModel) -> TiDetailRead:
    return TiDetailRead(
        id=rec.id,
        responden_id=rec.responden_id,
        sesi_id=rec.sesi_id,
        task_kode=rec.task_kode,
        sumber_bukti=rec.sumber_bukti,  # type: ignore[arg-type]
        kondisi=rec.kondisi,  # type: ignore[arg-type]
        frekuensi_teks=rec.frekuensi_teks,
        durasi_per_kali=rec.durasi_per_kali,
        jam_per_minggu=rec.jam_per_minggu,
        peak4w_hours=rec.peak4w_hours,
        ai_mode=rec.ai_mode,  # type: ignore[arg-type]
        va_type=rec.va_type,  # type: ignore[arg-type]
        dcs_flag=rec.dcs_flag,
        catatan=rec.catatan,
    )


class SqlTiDetailService:
    """`TiDetailService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def submit(
        self, responden_id: str, sesi_id: str, data: TiDetailSubmit, valid_kodes: set[str]
    ) -> list[TiDetailRead]:
        kodes = [item.task_kode for item in data.detail]
        if len(kodes) != len(set(kodes)):
            raise ValidationAppError("Terdapat task_kode duplikat dalam payload detail.")
        unknown = set(kodes) - valid_kodes
        if unknown:
            raise ValidationAppError(
                f"task_kode di luar himpunan terpilih: {', '.join(sorted(unknown)[:5])}"
                + ("..." if len(unknown) > 5 else ".")
            )
        already = self._s.scalar(
            select(TiDetailModel.id).where(TiDetailModel.responden_id == responden_id)
        )
        if already is not None:
            raise ConflictError(f"Responden '{responden_id}' sudah submit detail Tahap 2.")
        new: list[TiDetailModel] = []
        for item in data.detail:
            rec = TiDetailModel(
                id=f"tdet_{uuid.uuid4().hex[:8]}",
                responden_id=responden_id,
                sesi_id=sesi_id,
                task_kode=item.task_kode,
                sumber_bukti=item.sumber_bukti,
                kondisi=item.kondisi,
                frekuensi_teks=item.frekuensi_teks,
                durasi_per_kali=item.durasi_per_kali,
                jam_per_minggu=item.jam_per_minggu,
                peak4w_hours=item.peak4w_hours,
                ai_mode=item.ai_mode,
                va_type=item.va_type,
                dcs_flag=item.dcs_flag,
                catatan=item.catatan,
            )
            self._s.add(rec)
            new.append(rec)
        self._s.flush()
        return [_to_read(r) for r in new]

    def list_by_responden(self, responden_id: str) -> list[TiDetailRead]:
        rows = self._s.scalars(
            select(TiDetailModel)
            .where(TiDetailModel.responden_id == responden_id)
            .order_by(TiDetailModel.task_kode)
        ).all()
        return [_to_read(r) for r in rows]

    def list_by_sesi(self, sesi_id: str) -> list[TiDetailRead]:
        rows = self._s.scalars(
            select(TiDetailModel)
            .where(TiDetailModel.sesi_id == sesi_id)
            .order_by(TiDetailModel.task_kode, TiDetailModel.responden_id)
        ).all()
        return [_to_read(r) for r in rows]

    def count_responden_submitted(self, sesi_id: str) -> int:
        return (
            self._s.scalar(
                select(func.count(func.distinct(TiDetailModel.responden_id))).where(
                    TiDetailModel.sesi_id == sesi_id
                )
            )
            or 0
        )

    def delete_by_responden(self, responden_id: str) -> None:
        rows = self._s.scalars(
            select(TiDetailModel).where(TiDetailModel.responden_id == responden_id)
        ).all()
        for rec in rows:
            self._s.delete(rec)
        self._s.flush()
