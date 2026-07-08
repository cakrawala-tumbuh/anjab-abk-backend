"""Implementasi `TiDetailService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryTiDetailService` TANPA mengubah kontrak Protocol.

Satu baris per (responden, task_kode) di `ti_detail`. `upsert` melakukan
get-or-update per task_kode (harus termasuk himpunan terpilih sesi) sehingga
draft boleh disimpan berulang kali sebelum finalisasi. `submit` hanya
memvalidasi minimal 1 baris sudah ada di DB lalu mengembalikannya.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import ValidationAppError
from ...models import TiDetailModel
from ..schemas.detail import TiDetailRead, TiDetailUpsert


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

    def upsert(
        self, responden_id: str, sesi_id: str, data: TiDetailUpsert, valid_kodes: set[str]
    ) -> list[TiDetailRead]:
        kodes = [item.task_kode for item in data.detail]
        unknown = set(kodes) - valid_kodes
        if unknown:
            raise ValidationAppError(
                f"task_kode di luar himpunan terpilih: {', '.join(sorted(unknown)[:5])}"
                + ("..." if len(unknown) > 5 else ".")
            )
        results: list[TiDetailModel] = []
        for item in data.detail:
            existing = self._s.scalar(
                select(TiDetailModel).where(
                    TiDetailModel.responden_id == responden_id,
                    TiDetailModel.task_kode == item.task_kode,
                )
            )
            if existing is not None:
                existing.sumber_bukti = item.sumber_bukti
                existing.kondisi = item.kondisi
                existing.frekuensi_teks = item.frekuensi_teks
                existing.durasi_per_kali = item.durasi_per_kali
                existing.jam_per_minggu = item.jam_per_minggu
                existing.peak4w_hours = item.peak4w_hours
                existing.ai_mode = item.ai_mode
                existing.va_type = item.va_type
                existing.dcs_flag = item.dcs_flag
                existing.catatan = item.catatan
                results.append(existing)
            else:
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
                results.append(rec)
        self._s.flush()
        return [_to_read(r) for r in results]

    def submit(self, responden_id: str) -> list[TiDetailRead]:
        rows = self.list_by_responden(responden_id)
        if not rows:
            raise ValidationAppError(
                "Responden harus mengisi minimal 1 entri detail sebelum submit Tahap 3."
            )
        return rows

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
