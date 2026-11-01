"""Implementasi `BuktiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...models import (
    RedesainBuktiModel,
    RedesainKodeOrangModel,
    RedesainLangkahModel,
    RedesainMasalahModel,
    RedesainProsesModel,
)
from ...schemas.search import Domain, Order
from ...services.domain import validate_searchable_fields
from ...services.domain_sql import FieldMap, FieldSpec, compile_domain, order_by_columns
from ..schemas.bukti import BuktiCreate, BuktiRead, BuktiUpdate
from .bukti import SEARCHABLE_FIELDS
from .riwayat import RiwayatService

ENTITAS = "bukti"
PREFIX = "B-"

_KOLOM_EDIT = (
    "masalah_id",
    "langkah_id",
    "unit_periode",
    "jenis",
    "pembuat_kode_orang",
    "pembuat_peran",
    "independen",
    "klaim_didukung",
    "klaim_tidak_didukung",
    "tanggal_versi_lokasi",
    "status_pemeriksaan",
    "pemeriksa_kode_orang",
    "alasan",
    "catatan_privasi_gap",
)
_WAJIB = frozenset(
    {
        "unit_periode",
        "jenis",
        "independen",
        "klaim_didukung",
        "tanggal_versi_lokasi",
        "status_pemeriksaan",
    }
)


def _field_map() -> FieldMap:
    m = RedesainBuktiModel
    return {
        "id": FieldSpec(column=m.id),
        "kode": FieldSpec(column=m.kode),
        "masalah_id": FieldSpec(column=m.masalah_id),
        "langkah_id": FieldSpec(column=m.langkah_id),
        "jenis": FieldSpec(column=m.jenis),
        "status_pemeriksaan": FieldSpec(column=m.status_pemeriksaan),
        "independen": FieldSpec(column=m.independen),
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_read(rec: RedesainBuktiModel) -> BuktiRead:
    return BuktiRead(
        id=rec.id,
        kode=rec.kode,
        created_at=_aware(rec.created_at),
        updated_at=_aware(rec.updated_at),
        **{k: getattr(rec, k) for k in _KOLOM_EDIT},  # type: ignore[arg-type]
    )


def snapshot(r: BuktiRead) -> dict[str, object]:
    """Snapshot JSON-aman sebuah bukti untuk kolom nilai_sebelum/sesudah riwayat.

    Args:
        r: Bukti hasil baca.

    Returns:
        Dict kode + kolom bisnis (tanpa id dan cap waktu).
    """
    return {"kode": r.kode, **{k: getattr(r, k) for k in _KOLOM_EDIT}}


def _nomor_berikutnya(kode_ada: list[str]) -> int:
    """Nomor urut maksimum + 1 di antara kode `B-<angka>` (akhiran non-angka diabaikan)."""
    nomor = 0
    for kode in kode_ada:
        akhiran = kode[len(PREFIX) :]
        if kode.startswith(PREFIX) and akhiran.isdigit():
            nomor = max(nomor, int(akhiran))
    return nomor + 1


class SqlBuktiService:
    """`BuktiService` berbasis PostgreSQL; terikat satu `Session` per request.

    Masalah, langkah, dan kode orang (semua domain redesain) dibaca langsung dari tabelnya.
    Kode dibangkitkan maksimum + 1; bentrok akibat balapan berakhir 409 lewat unique `kode`.
    """

    def __init__(self, session: Session, riwayat: RiwayatService) -> None:
        self._s = session
        self._riwayat = riwayat

    def _validasi_kode_orang(self, kode: str | None, nama_field: str) -> None:
        if kode is None:
            return
        m = RedesainKodeOrangModel
        if self._s.scalar(select(func.count()).select_from(m).where(m.kode == kode)) == 0:
            raise ValidationAppError(f"Kode orang '{kode}' ({nama_field}) tidak dikenal.")

    def _validasi_rujukan(self, masalah_id: str, langkah_id: str | None) -> None:
        if self._s.get(RedesainMasalahModel, masalah_id) is None:
            raise ValidationAppError(f"Masalah '{masalah_id}' tidak ditemukan.")
        if langkah_id is None:
            return
        pr, lk = RedesainProsesModel, RedesainLangkahModel
        milik = self._s.scalar(
            select(func.count())
            .select_from(lk)
            .join(pr, pr.id == lk.proses_id)
            .where(lk.id == langkah_id, pr.masalah_id == masalah_id)
        )
        if not milik:
            raise ValidationAppError(
                f"Langkah '{langkah_id}' tidak ditemukan atau bukan milik proses masalah ini."
            )

    def _flush(self) -> None:
        try:
            self._s.flush()
        except IntegrityError as exc:
            raise ConflictError("Kode bukti bentrok; ulangi permintaan.") from exc

    def create(self, data: BuktiCreate, *, pelaku_kode_orang: str | None) -> BuktiRead:
        """Buat bukti berkode `B-NNNN` dan catat riwayat; rujukan divalidasi sebelum tulis.

        Raises:
            ValidationAppError: masalah/langkah/kode orang tak dikenal, atau langkah bukan
                milik proses masalah ini.
            ConflictError: kode hasil bangkitan bentrok (balapan dua create).
        """
        self._validasi_rujukan(data.masalah_id, data.langkah_id)
        self._validasi_kode_orang(data.pembuat_kode_orang, "pembuat")
        self._validasi_kode_orang(data.pemeriksa_kode_orang, "pemeriksa")
        m = RedesainBuktiModel
        kode_ada = list(self._s.scalars(select(m.kode).where(m.kode.like(f"{PREFIX}%"))))
        kode = f"{PREFIX}{_nomor_berikutnya(kode_ada):04d}"
        rec = m(id=str(uuid.uuid4()), kode=kode, **data.model_dump())
        self._s.add(rec)
        self._flush()
        self._s.refresh(rec)
        read = _to_read(rec)
        self._riwayat.catat(ENTITAS, read.id, "create", None, snapshot(read), pelaku_kode_orang)
        return read

    def _get_model(self, bukti_id: str) -> RedesainBuktiModel:
        rec = self._s.get(RedesainBuktiModel, bukti_id)
        if rec is None:
            raise NotFoundError(f"Bukti '{bukti_id}' tidak ditemukan.")
        return rec

    def get(self, bukti_id: str) -> BuktiRead:
        """Ambil satu bukti; `NotFoundError` (404) bila tak ada."""
        return _to_read(self._get_model(bukti_id))

    def list(self, *, limit: int, offset: int) -> tuple[list[BuktiRead], int]:
        """Daftar berurutan menurut `kode`."""
        m = RedesainBuktiModel
        total = self._s.scalar(select(func.count()).select_from(m)) or 0
        rows = self._s.scalars(select(m).order_by(m.kode).limit(limit).offset(offset)).all()
        return [_to_read(r) for r in rows], total

    def search(
        self, *, domain: Domain, order: Order, limit: int, offset: int
    ) -> tuple[list[BuktiRead], int]:
        """Cari memakai domain ala Odoo (field di-whitelist, nilai bound parameter)."""
        validate_searchable_fields(domain, order, SEARCHABLE_FIELDS)
        m = RedesainBuktiModel
        field_map = _field_map()
        cond = compile_domain(domain, field_map)
        order_cols = order_by_columns(order, field_map) or [m.kode]
        total = self._s.scalar(select(func.count()).select_from(m).where(cond)) or 0
        rows = self._s.scalars(
            select(m).where(cond).order_by(*order_cols).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def update(
        self, bukti_id: str, data: BuktiUpdate, *, pelaku_kode_orang: str | None
    ) -> BuktiRead:
        """Ubah parsial bukti (hanya field yang dikirim) dan catat riwayat.

        Field nullable boleh dikosongkan dengan `null`; field wajib bernilai `null` diabaikan.

        Raises:
            NotFoundError: bukti tidak ada.
            ValidationAppError: langkah/kode orang baru tak valid.
        """
        rec = self._get_model(bukti_id)
        sebelum = snapshot(_to_read(rec))
        terkirim = data.model_fields_set
        if "langkah_id" in terkirim:
            self._validasi_rujukan(rec.masalah_id, data.langkah_id)
        if "pembuat_kode_orang" in terkirim:
            self._validasi_kode_orang(data.pembuat_kode_orang, "pembuat")
        if "pemeriksa_kode_orang" in terkirim:
            self._validasi_kode_orang(data.pemeriksa_kode_orang, "pemeriksa")
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
