"""Implementasi `VersiMetodeService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError
from ...models import RedesainVersiMetodeModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.versi_metode import VersiMetodeCreate, VersiMetodeRead, VersiMetodeUpdate
from .riwayat import RiwayatService
from .versi_metode import SEARCHABLE_FIELDS

ENTITAS = "versi_metode"

_KOLOM = (
    "versi",
    "tanggal",
    "bagian",
    "apa_diperbarui",
    "alasan_risiko",
    "status_hasil_uji",
    "pemeriksa_pemutus",
)


def _field_map() -> FieldMap:
    m = RedesainVersiMetodeModel
    return {
        "id": FieldSpec(column=m.id),
        "versi": FieldSpec(column=m.versi),
        "bagian": FieldSpec(column=m.bagian),
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_read(rec: RedesainVersiMetodeModel) -> VersiMetodeRead:
    return VersiMetodeRead(
        id=rec.id,
        created_at=_aware(rec.created_at),
        updated_at=_aware(rec.updated_at),
        **{k: getattr(rec, k) for k in _KOLOM},
    )


def snapshot(r: VersiMetodeRead) -> dict[str, object]:
    """Snapshot JSON-aman sebuah catatan untuk kolom nilai_sebelum/sesudah riwayat.

    Args:
        r: Catatan hasil baca.

    Returns:
        Dict kolom bisnis (tanggal sebagai ISO 8601; tanpa id dan cap waktu).
    """
    nilai = {k: getattr(r, k) for k in _KOLOM}
    nilai["tanggal"] = r.tanggal.isoformat()
    return nilai


class SqlVersiMetodeService:
    """`VersiMetodeService` berbasis PostgreSQL; terikat satu `Session` per request."""

    def __init__(self, session: Session, riwayat: RiwayatService) -> None:
        self._s = session
        self._riwayat = riwayat

    def _flush(self) -> None:
        try:
            self._s.flush()
        except IntegrityError as exc:
            raise ConflictError("Catatan untuk pasangan versi dan bagian itu sudah ada.") from exc

    def create(self, data: VersiMetodeCreate, *, pelaku_kode_orang: str | None) -> VersiMetodeRead:
        """Buat catatan versi dan catat riwayat.

        Raises:
            ConflictError: pasangan `versi`+`bagian` sudah ada.
        """
        rec = RedesainVersiMetodeModel(id=str(uuid.uuid4()), **data.model_dump())
        self._s.add(rec)
        self._flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "create", None, snapshot(read), pelaku_kode_orang)
        return read

    def _get_model(self, versi_id: str) -> RedesainVersiMetodeModel:
        rec = self._s.get(RedesainVersiMetodeModel, versi_id)
        if rec is None:
            raise NotFoundError(f"Catatan versi metode '{versi_id}' tidak ditemukan.")
        return rec

    def get(self, versi_id: str) -> VersiMetodeRead:
        """Ambil satu catatan; `NotFoundError` (404) bila tak ada."""
        return _to_read(self._get_model(versi_id))

    def list(self, *, limit: int, offset: int) -> tuple[list[VersiMetodeRead], int]:
        """Daftar berurutan menurut tanggal, versi, lalu bagian."""
        m = RedesainVersiMetodeModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(
            select(m).order_by(m.tanggal, m.versi, m.bagian).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[VersiMetodeRead], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = RedesainVersiMetodeModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.tanggal, m.versi, m.bagian]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def update(
        self, versi_id: str, data: VersiMetodeUpdate, *, pelaku_kode_orang: str | None
    ) -> VersiMetodeRead:
        """Ubah parsial catatan (hanya field yang dikirim, `null` diabaikan) dan catat riwayat.

        Raises:
            NotFoundError: catatan tidak ada.
            ConflictError: perubahan membuat pasangan `versi`+`bagian` bentrok.
        """
        rec = self._get_model(versi_id)
        sebelum = snapshot(_to_read(rec))
        for nama in data.model_fields_set:
            nilai = getattr(data, nama)
            if nilai is not None:
                setattr(rec, nama, nilai)
        self._flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "update", sebelum, snapshot(read), pelaku_kode_orang)
        return read
