"""Implementasi `CakupanJabatanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...anjab.services.jabatan import JabatanService
from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import RedesainCakupanJabatanModel, RedesainKodeOrangModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.cakupan_jabatan import (
    CakupanJabatanCreate,
    CakupanJabatanRead,
    CakupanJabatanUpdate,
)
from .cakupan_jabatan import SEARCHABLE_FIELDS
from .riwayat import RiwayatService

ENTITAS = "cakupan_jabatan"

_KOLOM_EDIT = (
    "role_kode",
    "nama_jabatan",
    "jabatan_id",
    "cabang",
    "status_unit",
    "pemegang_diperiksa",
    "inventori_ditinjau",
    "peta_diperkuat",
    "gap_variasi",
    "pic_kode_orang",
)
_WAJIB = frozenset(
    {"nama_jabatan", "status_unit", "pemegang_diperiksa", "inventori_ditinjau", "peta_diperkuat"}
)


def _field_map() -> FieldMap:
    m = RedesainCakupanJabatanModel
    return {
        "id": FieldSpec(column=m.id),
        "role_kode": FieldSpec(column=m.role_kode),
        "cabang": FieldSpec(column=m.cabang),
        "status_unit": FieldSpec(column=m.status_unit),
        "jabatan_id": FieldSpec(column=m.jabatan_id),
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_read(rec: RedesainCakupanJabatanModel) -> CakupanJabatanRead:
    return CakupanJabatanRead(
        id=rec.id,
        created_at=_aware(rec.created_at),
        updated_at=_aware(rec.updated_at),
        **{k: getattr(rec, k) for k in _KOLOM_EDIT},  # type: ignore[arg-type]
    )


def snapshot(r: CakupanJabatanRead) -> dict[str, object]:
    """Snapshot JSON-aman sebuah entri cakupan untuk kolom nilai_sebelum/sesudah riwayat.

    Args:
        r: Entri hasil baca.

    Returns:
        Dict kolom bisnis (tanpa id dan cap waktu).
    """
    return {k: getattr(r, k) for k in _KOLOM_EDIT}


class SqlCakupanJabatanService:
    """`CakupanJabatanService` berbasis PostgreSQL; terikat satu `Session` per request.

    Keberadaan jabatan divalidasi lewat seam `JabatanService` (domain anjab), bukan query
    langsung. Pemetaan nama paket ke master jabatan sepenuhnya manual (tidak ada auto-match).
    """

    def __init__(self, session: Session, riwayat: RiwayatService, jabatan: JabatanService) -> None:
        self._s = session
        self._riwayat = riwayat
        self._jabatan = jabatan

    def _validasi_jabatan(self, jabatan_id: str | None) -> None:
        if jabatan_id is None:
            return
        try:
            self._jabatan.get(jabatan_id)
        except NotFoundError as exc:
            raise ValidationAppError(f"Jabatan '{jabatan_id}' tidak ditemukan.") from exc

    def _validasi_kode_orang(self, kode: str | None) -> None:
        if kode is None:
            return
        m = RedesainKodeOrangModel
        if self._s.scalar(select(func.count()).select_from(m).where(m.kode == kode)) == 0:
            raise ValidationAppError(f"Kode orang '{kode}' (PIC) tidak dikenal.")

    def create(
        self, data: CakupanJabatanCreate, *, pelaku_kode_orang: str | None
    ) -> CakupanJabatanRead:
        """Buat entri cakupan (satu cabang) dan catat riwayat.

        Raises:
            ValidationAppError: jabatan/kode orang tak dikenal.
            ConflictError: pasangan `role_kode`+`cabang` sudah ada.
        """
        self._validasi_jabatan(data.jabatan_id)
        self._validasi_kode_orang(data.pic_kode_orang)
        m = RedesainCakupanJabatanModel
        ada = self._s.scalar(
            select(func.count())
            .select_from(m)
            .where(m.role_kode == data.role_kode, m.cabang == data.cabang)
        )
        if ada:
            raise ConflictError(
                f"Cakupan '{data.role_kode}' untuk cabang '{data.cabang}' sudah ada."
            )
        rec = m(id=str(uuid.uuid4()), **data.model_dump())
        self._s.add(rec)
        try:
            self._s.flush()
        except IntegrityError as exc:
            raise ConflictError("Pasangan role_kode dan cabang sudah ada.") from exc
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "create", None, snapshot(read), pelaku_kode_orang)
        return read

    def _get_model(self, cakupan_id: str) -> RedesainCakupanJabatanModel:
        rec = self._s.get(RedesainCakupanJabatanModel, cakupan_id)
        if rec is None:
            raise NotFoundError(f"Cakupan jabatan '{cakupan_id}' tidak ditemukan.")
        return rec

    def get(self, cakupan_id: str) -> CakupanJabatanRead:
        """Ambil satu entri; `NotFoundError` (404) bila tak ada."""
        return _to_read(self._get_model(cakupan_id))

    def list(self, *, limit: int, offset: int) -> tuple[list[CakupanJabatanRead], int]:
        """Daftar berurutan menurut `role_kode` lalu `cabang`."""
        m = RedesainCakupanJabatanModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(
            select(m).order_by(m.role_kode, m.cabang).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[CakupanJabatanRead], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = RedesainCakupanJabatanModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.role_kode, m.cabang]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def update(
        self, cakupan_id: str, data: CakupanJabatanUpdate, *, pelaku_kode_orang: str | None
    ) -> CakupanJabatanRead:
        """Ubah parsial entri (hanya field yang dikirim) dan catat riwayat.

        Field nullable boleh dikosongkan dengan `null`; field wajib bernilai `null`
        diabaikan.

        Raises:
            NotFoundError: entri tidak ada.
            ValidationAppError: jabatan/kode orang baru tak dikenal.
        """
        rec = self._get_model(cakupan_id)
        sebelum = snapshot(_to_read(rec))
        terkirim = data.model_fields_set
        if "jabatan_id" in terkirim:
            self._validasi_jabatan(data.jabatan_id)
        if "pic_kode_orang" in terkirim:
            self._validasi_kode_orang(data.pic_kode_orang)
        for nama in terkirim:
            nilai = getattr(data, nama)
            if nilai is None and nama in _WAJIB:
                continue
            setattr(rec, nama, nilai)
        self._s.flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "update", sebelum, snapshot(read), pelaku_kode_orang)
        return read
