"""Implementasi `JabatanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

MENGGANTI `InMemoryJabatanService` (placeholder seam) TANPA mengubah kontrak
`JabatanService` (Protocol) — signature method identik, sehingga router, skema,
dan error envelope tidak ikut berubah.

Pemetaan error ke hierarki `AppError`:
- baris tak ada           → `NotFoundError` (404)
- `kode` duplikat/konflik → `ConflictError` (409)

Whitelist field search dipakai ULANG dari `anjab.services.jabatan.SEARCHABLE_FIELDS`
(satu sumber), lalu dipetakan ke kolom lewat `domain_sql.FieldSpec`.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError
from ...models import JabatanModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.jabatan import JabatanCreate, JabatanRead, JabatanUpdate

# Sumber tunggal whitelist (didefinisikan di seam placeholder InMemory).
from .jabatan import SEARCHABLE_FIELDS


def jabatan_field_map() -> FieldMap:
    """Petakan field ter-whitelist → kolom PostgreSQL."""
    return {
        "id": FieldSpec(column=JabatanModel.id),
        "kode": FieldSpec(column=JabatanModel.kode),
        "nama": FieldSpec(column=JabatanModel.nama),
        "jenis": FieldSpec(column=JabatanModel.jenis),
        "unit_kerja_id": FieldSpec(column=JabatanModel.unit_kerja_id),
        "aktif": FieldSpec(column=JabatanModel.aktif),
        "created_at": FieldSpec(
            column=JabatanModel.created_at, order_column=JabatanModel.created_at
        ),
    }


def _to_read(rec: JabatanModel) -> JabatanRead:
    """Petakan model penyimpanan → skema API (skema ≠ model penyimpanan)."""
    created = rec.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return JabatanRead(
        id=rec.id,
        kode=rec.kode,
        nama=rec.nama,
        jenis=rec.jenis,  # type: ignore[arg-type]
        unit_kerja_id=rec.unit_kerja_id,
        deskripsi=rec.deskripsi,
        aktif=rec.aktif,
        created_at=created,
    )


class SqlJabatanService:
    """`JabatanService` berbasis PostgreSQL. Terikat pada satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def _get_model(self, jabatan_id: str) -> JabatanModel:
        rec = self._s.get(JabatanModel, jabatan_id)
        if rec is None:
            raise NotFoundError(f"Jabatan '{jabatan_id}' tidak ditemukan.")
        return rec

    def _flush_checked(self, *, on_conflict: str) -> None:
        """Flush dalam SAVEPOINT; petakan `IntegrityError` (duplikat unik) → 409.

        SAVEPOINT (`begin_nested`) WAJIB di PostgreSQL: error membatalkan seluruh
        transaksi sampai di-rollback; dengan savepoint rollback hanya ke savepoint
        sehingga transaksi request tetap sehat.
        """
        try:
            with self._s.begin_nested():
                self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(on_conflict) from exc

    def list(self, *, limit: int, offset: int) -> tuple[list[JabatanRead], int]:
        total = self._s.scalar(select(func.count()).select_from(JabatanModel)) or 0
        rows = self._s.scalars(
            select(JabatanModel).order_by(JabatanModel.nama).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def get(self, jabatan_id: str) -> JabatanRead:
        return _to_read(self._get_model(jabatan_id))

    def create(self, data: JabatanCreate) -> JabatanRead:
        # Pre-cek kode untuk pesan ramah; unique constraint tetap jadi backstop balapan.
        exists = self._s.scalar(select(JabatanModel.id).where(JabatanModel.kode == data.kode))
        if exists is not None:
            raise ConflictError(f"Jabatan dengan kode '{data.kode}' sudah ada.")
        rec = JabatanModel(
            id=f"jbt_{uuid.uuid4().hex[:8]}",
            kode=data.kode,
            nama=data.nama,
            jenis=data.jenis,
            unit_kerja_id=data.unit_kerja_id,
            deskripsi=data.deskripsi,
            aktif=data.aktif,
        )
        self._s.add(rec)
        self._flush_checked(on_conflict=f"Jabatan dengan kode '{data.kode}' sudah ada.")
        return _to_read(rec)

    def update(self, jabatan_id: str, data: JabatanUpdate) -> JabatanRead:
        rec = self._get_model(jabatan_id)
        changes = data.model_dump(exclude_unset=True)  # semantik PATCH yang benar
        if "kode" in changes:
            clash = self._s.scalar(
                select(JabatanModel.id).where(
                    JabatanModel.kode == changes["kode"], JabatanModel.id != jabatan_id
                )
            )
            if clash is not None:
                raise ConflictError(f"Jabatan dengan kode '{changes['kode']}' sudah ada.")
        for key, value in changes.items():
            setattr(rec, key, value)
        self._flush_checked(on_conflict="Pembaruan melanggar batasan keunikan.")
        return _to_read(rec)

    def delete(self, jabatan_id: str) -> None:
        rec = self._get_model(jabatan_id)
        self._s.delete(rec)
        self._flush_checked(on_conflict="Tidak dapat menghapus jabatan.")

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[JabatanRead], int]:
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)  # 422 bila field asing
        field_map = jabatan_field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [JabatanModel.nama]
        total = self._s.scalar(select(func.count()).select_from(JabatanModel).where(cond)) or 0
        rows = self._s.scalars(
            select(JabatanModel).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total
