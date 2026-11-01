"""Implementasi `KonteksService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError
from ...models import RedesainKonteksModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.konteks import KonteksCreate, KonteksRead, KonteksUpdate
from .konteks import SEARCHABLE_FIELDS
from .riwayat import RiwayatService

ENTITAS = "konteks"

_KOLOM_EDIT = (
    "tema",
    "gelombang",
    "ruang_dugaan",
    "sumber_draft",
    "batas_pemeriksaan",
    "aktif",
)


def _field_map() -> FieldMap:
    m = RedesainKonteksModel
    return {
        "id": FieldSpec(column=m.id),
        "kode": FieldSpec(column=m.kode),
        "tema": FieldSpec(column=m.tema),
        "gelombang": FieldSpec(column=m.gelombang),
        "aktif": FieldSpec(column=m.aktif),
        "created_at": FieldSpec(column=m.created_at, order_column=m.created_at),
        "updated_at": FieldSpec(column=m.updated_at, order_column=m.updated_at),
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_read(rec: RedesainKonteksModel) -> KonteksRead:
    return KonteksRead(
        id=rec.id,
        kode=rec.kode,
        tema=rec.tema,
        gelombang=rec.gelombang,  # type: ignore[arg-type]
        ruang_dugaan=rec.ruang_dugaan,
        sumber_draft=rec.sumber_draft,
        batas_pemeriksaan=rec.batas_pemeriksaan,
        aktif=rec.aktif,
        created_at=_aware(rec.created_at),
        updated_at=_aware(rec.updated_at),
    )


def snapshot(r: KonteksRead) -> dict[str, object]:
    """Snapshot JSON-aman sebuah konteks untuk kolom nilai_sebelum/sesudah riwayat.

    Args:
        r: Konteks hasil baca.

    Returns:
        Dict kolom bisnis (tanpa id dan cap waktu).
    """
    return {"kode": r.kode, **{k: getattr(r, k) for k in _KOLOM_EDIT}}


class SqlKonteksService:
    """`KonteksService` berbasis PostgreSQL; terikat satu `Session` per request."""

    def __init__(self, session: Session, riwayat: RiwayatService) -> None:
        self._s = session
        self._riwayat = riwayat

    def create(self, data: KonteksCreate, *, pelaku_kode_orang: str | None) -> KonteksRead:
        """Buat konteks baru dan catat riwayat.

        Raises:
            ConflictError: `kode` sudah dipakai.
        """
        m = RedesainKonteksModel
        if self._s.scalars(select(m.id).where(m.kode == data.kode)).first() is not None:
            raise ConflictError(f"Konteks '{data.kode}' sudah ada.")
        rec = m(id=str(uuid.uuid4()), **data.model_dump())
        self._s.add(rec)
        self._s.flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "create", None, snapshot(read), pelaku_kode_orang)
        return read

    def _get_model(self, konteks_id: str) -> RedesainKonteksModel:
        rec = self._s.get(RedesainKonteksModel, konteks_id)
        if rec is None:
            raise NotFoundError(f"Konteks '{konteks_id}' tidak ditemukan.")
        return rec

    def get(self, konteks_id: str) -> KonteksRead:
        """Ambil satu konteks; `NotFoundError` (404) bila tak ada."""
        return _to_read(self._get_model(konteks_id))

    def list(self, *, limit: int, offset: int) -> tuple[list[KonteksRead], int]:
        """Daftar berurutan menurut `kode`."""
        m = RedesainKonteksModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(select(m).order_by(m.kode).limit(limit).offset(offset)).all()
        return [_to_read(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[KonteksRead], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = RedesainKonteksModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.kode]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def update(
        self, konteks_id: str, data: KonteksUpdate, *, pelaku_kode_orang: str | None
    ) -> KonteksRead:
        """Ubah parsial konteks (hanya field yang dikirim) dan catat riwayat.

        Raises:
            NotFoundError: Konteks tidak ada.
        """
        rec = self._get_model(konteks_id)
        sebelum = snapshot(_to_read(rec))
        for nama in data.model_fields_set:
            nilai = getattr(data, nama)
            if nilai is not None:
                setattr(rec, nama, nilai)
        self._s.flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "update", sebelum, snapshot(read), pelaku_kode_orang)
        return read
