"""Implementasi `NarasiSumberService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...errors import NotFoundError, ValidationAppError
from ...models import NarasiSumberModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.sumber import NarasiSumberCreate, NarasiSumberRead, NarasiSumberRingkas
from .sumber import SEARCHABLE_FIELDS


def hash_teks(teks: str) -> str:
    """Hitung SHA-256 heksadesimal atas UTF-8 `teks` persis seperti tersimpan.

    Args:
        teks: Teks sumber.

    Returns:
        String heksadesimal 64 karakter.
    """
    return hashlib.sha256(teks.encode("utf-8")).hexdigest()


def _field_map() -> FieldMap:
    m = NarasiSumberModel
    return {
        "jenis": FieldSpec(column=m.jenis),
        "periode": FieldSpec(column=m.periode),
        "judul": FieldSpec(column=m.judul),
        "izin_ai": FieldSpec(column=m.izin_ai),
        "created_at": FieldSpec(column=m.created_at),
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


_KOLOM_RINGKAS = (
    "id",
    "judul",
    "jenis",
    "versi",
    "periode",
    "teks_hash",
    "izin_ai",
    "izin_catatan",
    "menggantikan_id",
    "dibuat_oleh",
)


def _ringkas(rec: NarasiSumberModel) -> NarasiSumberRingkas:
    return NarasiSumberRingkas(
        created_at=_aware(rec.created_at),
        **{k: getattr(rec, k) for k in _KOLOM_RINGKAS},  # type: ignore[arg-type]
    )


def _to_read(rec: NarasiSumberModel) -> NarasiSumberRead:
    return NarasiSumberRead(**_ringkas(rec).model_dump(), teks=rec.teks)


class SqlNarasiSumberService:
    """`NarasiSumberService` berbasis PostgreSQL; terikat satu `Session` per request.

    Baris tidak pernah diubah atau dihapus; revisi = baris baru dengan `menggantikan_id`.
    """

    def __init__(self, session: Session) -> None:
        self._s = session

    def create(self, data: NarasiSumberCreate, *, dibuat_oleh: str) -> NarasiSumberRead:
        """Simpan sumber baru; `teks_hash` dihitung dari teks.

        Raises:
            ValidationAppError: `menggantikan_id` tak dikenal.
        """
        if data.menggantikan_id is not None and (
            self._s.get(NarasiSumberModel, data.menggantikan_id) is None
        ):
            raise ValidationAppError(f"Sumber '{data.menggantikan_id}' tidak ditemukan.")
        rec = NarasiSumberModel(
            id=str(uuid.uuid4()),
            judul=data.judul,
            jenis=data.jenis.value,
            versi=data.versi,
            periode=data.periode,
            teks=data.teks,
            teks_hash=hash_teks(data.teks),
            izin_ai=data.izin_ai,
            izin_catatan=data.izin_catatan,
            menggantikan_id=data.menggantikan_id,
            dibuat_oleh=dibuat_oleh,
        )
        self._s.add(rec)
        self._s.flush()
        self._s.refresh(rec)
        return _to_read(rec)

    def get(self, sumber_id: str) -> NarasiSumberRead:
        """Ambil satu sumber; `NotFoundError` (404) bila tak ada."""
        rec = self._s.get(NarasiSumberModel, sumber_id)
        if rec is None:
            raise NotFoundError(f"Sumber narasi '{sumber_id}' tidak ditemukan.")
        return _to_read(rec)

    def list(
        self, *, jenis: str | None, periode: str | None, limit: int, offset: int
    ) -> tuple[list[NarasiSumberRingkas], int]:
        """Daftar ringkas terbaru dulu; filter `jenis`/`periode` opsional."""
        m = NarasiSumberModel
        conds = []
        if jenis is not None:
            conds.append(m.jenis == jenis)
        if periode is not None:
            conds.append(m.periode == periode)
        total = self._s.scalar(select(func.count()).select_from(m).where(*conds)) or 0
        rows = self._s.scalars(
            select(m).where(*conds).order_by(m.created_at.desc(), m.id).limit(limit).offset(offset)
        ).all()
        return [_ringkas(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[NarasiSumberRingkas], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = NarasiSumberModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.created_at.desc(), m.id]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_ringkas(r) for r in rows], total
