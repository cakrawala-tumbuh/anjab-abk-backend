"""Implementasi `PenilaianService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import RedesainMasalahModel, RedesainPenilaianModel
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.penilaian import PenilaianCreate, PenilaianRead, PenilaianUpdate
from ..triase import VERSI_ATURAN_TRIASE, hitung_saran
from .penilaian import SEARCHABLE_FIELDS
from .riwayat import RiwayatService

ENTITAS = "penilaian"

_KOLOM_EDIT = (
    "status_bukti",
    "gap_material",
    "indikasi_kritis",
    "k1",
    "k2",
    "k3",
    "k4",
    "alasan_rentang_beda",
    "diluruskan_sekolah",
    "pemeriksa_sekolah_konteks",
    "tindak_lanjut",
    "catatan_sumber_versi",
)
_KOLOM_HITUNG = ("saran_otomatis", "versi_aturan_triase")
_WAJIB = frozenset({"status_bukti", "gap_material", "indikasi_kritis"})


def _field_map() -> FieldMap:
    m = RedesainPenilaianModel
    return {
        "masalah_id": FieldSpec(column=m.masalah_id),
        "status_bukti": FieldSpec(column=m.status_bukti),
        "saran_otomatis": FieldSpec(column=m.saran_otomatis),
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_read(rec: RedesainPenilaianModel) -> PenilaianRead:
    return PenilaianRead(
        id=rec.id,
        masalah_id=rec.masalah_id,
        created_at=_aware(rec.created_at),
        updated_at=_aware(rec.updated_at),
        **{k: getattr(rec, k) for k in (*_KOLOM_EDIT, *_KOLOM_HITUNG)},  # type: ignore[arg-type]
    )


def snapshot(r: PenilaianRead) -> dict[str, object]:
    """Snapshot JSON-aman sebuah penilaian untuk kolom nilai_sebelum/sesudah riwayat.

    Args:
        r: Penilaian hasil baca.

    Returns:
        Dict `masalah_id` + kolom bisnis + `saran_otomatis`/`versi_aturan_triase`
        (tanpa id dan cap waktu).
    """
    return {
        "masalah_id": r.masalah_id,
        **{k: getattr(r, k) for k in (*_KOLOM_EDIT, *_KOLOM_HITUNG)},
    }


def _hitung_ulang(rec: RedesainPenilaianModel) -> None:
    """Isi `saran_otomatis` & `versi_aturan_triase` dari kolom penilaian saat ini (mutasi rec)."""
    rec.saran_otomatis = hitung_saran(
        rec.status_bukti, rec.gap_material, rec.indikasi_kritis, rec.k1, rec.k2, rec.k3, rec.k4
    )
    rec.versi_aturan_triase = VERSI_ATURAN_TRIASE


class SqlPenilaianService:
    """`PenilaianService` berbasis PostgreSQL; terikat satu `Session` per request.

    Satu penilaian per masalah: dicek eksplisit sebelum INSERT (409) dan dijaga unique
    `masalah_id` sebagai backstop balapan. Saran triase dihitung ulang setiap tulis.
    """

    def __init__(self, session: Session, riwayat: RiwayatService) -> None:
        self._s = session
        self._riwayat = riwayat

    def create(self, data: PenilaianCreate, *, pelaku_kode_orang: str | None) -> PenilaianRead:
        """Buat penilaian, hitung saran triase, dan catat riwayat.

        Raises:
            ValidationAppError: masalah tidak ditemukan (422).
            ConflictError: masalah sudah punya penilaian (409).
        """
        if self._s.get(RedesainMasalahModel, data.masalah_id) is None:
            raise ValidationAppError(f"Masalah '{data.masalah_id}' tidak ditemukan.")
        m = RedesainPenilaianModel
        sudah = self._s.scalar(
            select(func.count()).select_from(m).where(m.masalah_id == data.masalah_id)
        )
        if sudah:
            raise ConflictError(f"Masalah '{data.masalah_id}' sudah punya penilaian.")
        rec = m(id=str(uuid.uuid4()), **data.model_dump())
        _hitung_ulang(rec)
        self._s.add(rec)
        try:
            self._s.flush()
        except IntegrityError as exc:
            raise ConflictError(f"Masalah '{data.masalah_id}' sudah punya penilaian.") from exc
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "create", None, snapshot(read), pelaku_kode_orang)
        return read

    def _get_model(self, penilaian_id: str) -> RedesainPenilaianModel:
        rec = self._s.get(RedesainPenilaianModel, penilaian_id)
        if rec is None:
            raise NotFoundError(f"Penilaian '{penilaian_id}' tidak ditemukan.")
        return rec

    def get(self, penilaian_id: str) -> PenilaianRead:
        """Ambil satu penilaian; `NotFoundError` (404) bila tak ada."""
        return _to_read(self._get_model(penilaian_id))

    def list(self, *, limit: int, offset: int) -> tuple[list[PenilaianRead], int]:
        """Daftar berurutan menurut `created_at` lalu `id`."""
        m = RedesainPenilaianModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(
            select(m).order_by(m.created_at, m.id).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[PenilaianRead], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = RedesainPenilaianModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.created_at, m.id]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def update(
        self, penilaian_id: str, data: PenilaianUpdate, *, pelaku_kode_orang: str | None
    ) -> PenilaianRead:
        """Ubah parsial penilaian, hitung ulang saran triase, dan catat riwayat.

        Field nullable boleh dikosongkan dengan `null`; field wajib bernilai `null` diabaikan.

        Raises:
            NotFoundError: penilaian tidak ada (404).
        """
        rec = self._get_model(penilaian_id)
        sebelum = snapshot(_to_read(rec))
        for nama in data.model_fields_set:
            nilai = getattr(data, nama)
            if nilai is None and nama in _WAJIB:
                continue
            setattr(rec, nama, nilai)
        _hitung_ulang(rec)
        self._s.flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "update", sebelum, snapshot(read), pelaku_kode_orang)
        return read
