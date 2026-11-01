"""Implementasi `RiwayatService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...models import RedesainRiwayatModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.riwayat import RiwayatRead
from .riwayat import SEARCHABLE_FIELDS


def _field_map() -> FieldMap:
    m = RedesainRiwayatModel
    return {
        "id": FieldSpec(column=m.id),
        "entitas": FieldSpec(column=m.entitas),
        "entitas_id": FieldSpec(column=m.entitas_id),
        "aksi": FieldSpec(column=m.aksi),
        "pelaku_kode_orang": FieldSpec(column=m.pelaku_kode_orang),
        "waktu": FieldSpec(column=m.waktu, order_column=m.waktu),
    }


def _to_read(rec: RedesainRiwayatModel) -> RiwayatRead:
    waktu = rec.waktu
    if waktu.tzinfo is None:
        waktu = waktu.replace(tzinfo=UTC)
    return RiwayatRead(
        id=rec.id,
        entitas=rec.entitas,
        entitas_id=rec.entitas_id,
        aksi=rec.aksi,
        nilai_sebelum=rec.nilai_sebelum,
        nilai_sesudah=rec.nilai_sesudah,
        pelaku_kode_orang=rec.pelaku_kode_orang,
        waktu=waktu,
    )


class SqlRiwayatService:
    """`RiwayatService` berbasis PostgreSQL; terikat satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def catat(
        self,
        entitas: str,
        entitas_id: str,
        aksi: str,
        sebelum: dict[str, Any] | None,
        sesudah: dict[str, Any] | None,
        pelaku_kode_orang: str | None,
    ) -> RiwayatRead:
        """Tambahkan satu baris riwayat lewat sesi yang sama dengan perubahan entitas.

        Args:
            entitas: Nama entitas (mis. `masalah`).
            entitas_id: ID entitas.
            aksi: Jenis aksi (`create`, `update`, `kirim`, `putuskan`, ...).
            sebelum: Snapshot JSON sebelum perubahan, atau None.
            sesudah: Snapshot JSON sesudah perubahan, atau None.
            pelaku_kode_orang: Kode pseudonim pelaku; None hanya untuk seed/sistem.

        Returns:
            Catatan yang tersimpan (setelah `flush`, belum commit).
        """
        rec = RedesainRiwayatModel(
            id=str(uuid.uuid4()),
            entitas=entitas,
            entitas_id=entitas_id,
            aksi=aksi,
            nilai_sebelum=sebelum,
            nilai_sesudah=sesudah,
            pelaku_kode_orang=pelaku_kode_orang,
        )
        self._s.add(rec)
        self._s.flush()
        return _to_read(rec)

    def list(
        self,
        *,
        entitas: str | None,
        entitas_id: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[RiwayatRead], int]:
        """Daftar riwayat terbaru dulu, opsional disaring `entitas`/`entitas_id`."""
        m = RedesainRiwayatModel
        conds = []
        if entitas is not None:
            conds.append(m.entitas == entitas)
        if entitas_id is not None:
            conds.append(m.entitas_id == entitas_id)
        total = self._s.scalar(select(func.count()).select_from(m).where(*conds)) or 0
        rows = self._s.scalars(
            select(m).where(*conds).order_by(m.waktu.desc(), m.id).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[RiwayatRead], int]:
        """Cari riwayat memakai domain ala Odoo (field di-whitelist, nilai bound param)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = RedesainRiwayatModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.waktu.desc()]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total
