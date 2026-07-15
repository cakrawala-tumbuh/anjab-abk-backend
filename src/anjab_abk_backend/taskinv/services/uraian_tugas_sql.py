"""Implementasi `UraianTugasService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryUraianTugasService` TANPA mengubah kontrak Protocol.

`kode` unik global. Validasi "jabatan_id ∈ jabatan_ids DetilTugas induk" (bila
detil_tugas_id diisi) direplikasi langsung lewat query DB ke `ti_detil_tugas`,
alih-alih memanggil service lain. Parameter `dt_svc` dipertahankan agar signature
kompatibel dengan InMemory, tetapi tidak diperlukan oleh implementasi SQL.
"""

from __future__ import annotations

import uuid
from datetime import UTC
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import TiDetilTugasModel, TiUraianTugasModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.uraian_tugas import UraianTugasCreate, UraianTugasRead, UraianTugasUpdate

# Sumber tunggal whitelist (didefinisikan di seam placeholder InMemory).
from .uraian_tugas import SEARCHABLE_FIELDS


def _uraian_tugas_field_map() -> FieldMap:
    return {
        "id": FieldSpec(column=TiUraianTugasModel.id),
        "kode": FieldSpec(column=TiUraianTugasModel.kode),
        "uraian": FieldSpec(column=TiUraianTugasModel.uraian),
        "unit": FieldSpec(column=TiUraianTugasModel.unit),
        "jabatan_id": FieldSpec(column=TiUraianTugasModel.jabatan_id),
        "urutan": FieldSpec(
            column=TiUraianTugasModel.urutan, order_column=TiUraianTugasModel.urutan
        ),
        "detil_tugas_id": FieldSpec(column=TiUraianTugasModel.detil_tugas_id),
        "tugas_pokok_id": FieldSpec(column=TiUraianTugasModel.tugas_pokok_id),
        "created_at": FieldSpec(
            column=TiUraianTugasModel.created_at, order_column=TiUraianTugasModel.created_at
        ),
    }


def _to_read(rec: TiUraianTugasModel) -> UraianTugasRead:
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return UraianTugasRead(
        id=rec.id,
        kode=rec.kode,
        uraian=rec.uraian,
        unit=rec.unit,
        jabatan_id=rec.jabatan_id,
        urutan=rec.urutan,
        detil_tugas_id=rec.detil_tugas_id,
        tugas_pokok_id=rec.tugas_pokok_id,
        std_sumber_bukti=rec.std_sumber_bukti,  # type: ignore[arg-type]
        std_kondisi=rec.std_kondisi,  # type: ignore[arg-type]
        std_frekuensi_teks=rec.std_frekuensi_teks,
        std_durasi_per_kali=rec.std_durasi_per_kali,
        std_jam_per_minggu=rec.std_jam_per_minggu,
        std_peak4w_hours=rec.std_peak4w_hours,
        std_va_type=rec.std_va_type,  # type: ignore[arg-type]
        created_at=created,
    )


class SqlUraianTugasService:
    """`UraianTugasService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session, *, dt_svc: Any | None = None) -> None:
        self._s = session
        self._dt = dt_svc  # tidak dipakai; validasi langsung lewat DB.

    def _get_model(self, ut_id: str) -> TiUraianTugasModel:
        rec = self._s.get(TiUraianTugasModel, ut_id)
        if rec is None:
            raise NotFoundError(f"UraianTugas '{ut_id}' tidak ditemukan.")
        return rec

    def _flush_checked(self, *, on_conflict: str) -> None:
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(on_conflict) from exc

    def _validate_jabatan_in_dt(self, jabatan_id: str, detil_tugas_id: str) -> None:
        dt = self._s.get(TiDetilTugasModel, detil_tugas_id)
        if dt is None:
            raise NotFoundError(f"DetilTugas '{detil_tugas_id}' tidak ditemukan.")
        if jabatan_id not in dt.jabatan_ids:
            raise ValidationAppError(
                f"Jabatan '{jabatan_id}' bukan bagian dari jabatan_ids"
                f" DetilTugas '{detil_tugas_id}'."
            )

    def list(self, *, limit: int, offset: int) -> tuple[list[UraianTugasRead], int]:
        total = self._s.scalar(select(func.count()).select_from(TiUraianTugasModel)) or 0
        rows = self._s.scalars(
            select(TiUraianTugasModel)
            .order_by(
                TiUraianTugasModel.jabatan_id,
                TiUraianTugasModel.unit,
                TiUraianTugasModel.urutan,
            )
            .limit(limit)
            .offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def get(self, ut_id: str) -> UraianTugasRead:
        return _to_read(self._get_model(ut_id))

    def get_by_kode(self, kode: str) -> UraianTugasRead:
        rec = self._s.scalar(select(TiUraianTugasModel).where(TiUraianTugasModel.kode == kode))
        if rec is None:
            raise NotFoundError(f"UraianTugas dengan kode '{kode}' tidak ditemukan.")
        return _to_read(rec)

    def create(self, data: UraianTugasCreate) -> UraianTugasRead:
        if data.detil_tugas_id:
            self._validate_jabatan_in_dt(data.jabatan_id, data.detil_tugas_id)
        exists = self._s.scalar(
            select(TiUraianTugasModel.id).where(TiUraianTugasModel.kode == data.kode)
        )
        if exists is not None:
            raise ConflictError(f"UraianTugas dengan kode '{data.kode}' sudah ada.")
        rec = TiUraianTugasModel(
            id=f"ut_{uuid.uuid4().hex[:8]}",
            kode=data.kode,
            uraian=data.uraian,
            unit=data.unit,
            jabatan_id=data.jabatan_id,
            urutan=data.urutan,
            detil_tugas_id=data.detil_tugas_id,
            tugas_pokok_id=data.tugas_pokok_id,
            std_sumber_bukti=data.std_sumber_bukti,
            std_kondisi=data.std_kondisi,
            std_frekuensi_teks=data.std_frekuensi_teks,
            std_durasi_per_kali=data.std_durasi_per_kali,
            std_jam_per_minggu=data.std_jam_per_minggu,
            std_peak4w_hours=data.std_peak4w_hours,
            std_va_type=data.std_va_type,
        )
        self._s.add(rec)
        self._flush_checked(on_conflict=f"UraianTugas dengan kode '{data.kode}' sudah ada.")
        return _to_read(rec)

    def update(self, ut_id: str, data: UraianTugasUpdate) -> UraianTugasRead:
        rec = self._get_model(ut_id)
        changes = data.model_dump(exclude_unset=True)
        if "kode" in changes and changes["kode"] != rec.kode:
            clash = self._s.scalar(
                select(TiUraianTugasModel.id).where(
                    TiUraianTugasModel.kode == changes["kode"], TiUraianTugasModel.id != ut_id
                )
            )
            if clash is not None:
                raise ConflictError(f"UraianTugas dengan kode '{changes['kode']}' sudah ada.")
        new_jabatan_id = changes.get("jabatan_id", rec.jabatan_id)
        new_detil_id = changes.get("detil_tugas_id", rec.detil_tugas_id)
        if new_detil_id and ("jabatan_id" in changes or "detil_tugas_id" in changes):
            self._validate_jabatan_in_dt(new_jabatan_id, new_detil_id)
        for key, value in changes.items():
            setattr(rec, key, value)
        self._flush_checked(on_conflict="Pembaruan melanggar batasan keunikan.")
        return _to_read(rec)

    def delete(self, ut_id: str) -> None:
        rec = self._get_model(ut_id)
        self._s.delete(rec)
        self._flush_checked(on_conflict="Tidak dapat menghapus UraianTugas.")

    def list_by_unit_jabatan(self, unit: str, jabatan_id: str) -> list[UraianTugasRead]:
        rows = self._s.scalars(
            select(TiUraianTugasModel)
            .where(TiUraianTugasModel.unit == unit, TiUraianTugasModel.jabatan_id == jabatan_id)
            .order_by(TiUraianTugasModel.urutan)
        ).all()
        return [_to_read(r) for r in rows]

    def list_by_jabatan(self, jabatan_id: str) -> list[UraianTugasRead]:
        rows = self._s.scalars(
            select(TiUraianTugasModel)
            .where(TiUraianTugasModel.jabatan_id == jabatan_id)
            .order_by(TiUraianTugasModel.unit, TiUraianTugasModel.urutan)
        ).all()
        return [_to_read(r) for r in rows]

    def list_by_detil_tugas(self, dt_id: str) -> list[UraianTugasRead]:
        rows = self._s.scalars(
            select(TiUraianTugasModel)
            .where(TiUraianTugasModel.detil_tugas_id == dt_id)
            .order_by(TiUraianTugasModel.unit, TiUraianTugasModel.urutan)
        ).all()
        return [_to_read(r) for r in rows]

    def list_by_tugas_pokok(self, tp_id: str) -> list[UraianTugasRead]:
        rows = self._s.scalars(
            select(TiUraianTugasModel)
            .where(TiUraianTugasModel.tugas_pokok_id == tp_id)
            .order_by(TiUraianTugasModel.unit, TiUraianTugasModel.urutan)
        ).all()
        return [_to_read(r) for r in rows]

    def valid_kodes(self, unit: str, jabatan_id: str) -> set[str]:
        rows = self._s.scalars(
            select(TiUraianTugasModel.kode).where(
                TiUraianTugasModel.unit == unit, TiUraianTugasModel.jabatan_id == jabatan_id
            )
        ).all()
        return set(rows)

    def valid_kodes_for_jabatan(self, jabatan_id: str) -> set[str]:
        rows = self._s.scalars(
            select(TiUraianTugasModel.kode).where(TiUraianTugasModel.jabatan_id == jabatan_id)
        ).all()
        return set(rows)

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[UraianTugasRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        field_map = _uraian_tugas_field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [
            TiUraianTugasModel.jabatan_id,
            TiUraianTugasModel.unit,
            TiUraianTugasModel.urutan,
        ]
        total = (
            self._s.scalar(select(func.count()).select_from(TiUraianTugasModel).where(cond)) or 0
        )
        rows = self._s.scalars(
            select(TiUraianTugasModel).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total
