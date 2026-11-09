"""Implementasi `RisetStatistikService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..errors import NotFoundError
from ..models import RisetProtokolModel, RisetStatistikModel
from ..schemas.riset_protokol import StatusProtokol
from ..schemas.riset_statistik import RisetStatistikCreate, RisetStatistikRead, StatusStatistik
from .riset_statistik import (
    PemverifikasiTidakIndependenError,
    ProtokolBelumTerkunciError,
    StatistikSudahTerverifikasiError,
)


def _aware(dt: datetime | None) -> datetime | None:
    """Pastikan datetime ber-zona waktu (UTC) sebelum masuk skema respons."""
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_read(rec: RisetStatistikModel) -> RisetStatistikRead:
    """Petakan baris ORM ke representasi respons."""
    return RisetStatistikRead(
        id=rec.id,
        protokol_id=rec.protokol_id,
        nama_analisis=rec.nama_analisis,
        keluaran=rec.keluaran,
        kode_sumber_ref=rec.kode_sumber_ref,
        status=StatusStatistik(rec.status),
        dibuat_oleh=rec.dibuat_oleh,
        diverifikasi_oleh=rec.diverifikasi_oleh,
        diverifikasi_pada=_aware(rec.diverifikasi_pada),
        created_at=_aware(rec.created_at),  # type: ignore[arg-type]
    )


class SqlRisetStatistikService:
    """`RisetStatistikService` berbasis PostgreSQL; terikat satu `Session` per request.

    Baris tidak pernah dihapus; satu-satunya perubahan adalah `verifikasi()` sekali jalan.
    """

    def __init__(self, session: Session) -> None:
        """Simpan sesi per-request yang dipakai seluruh operasi."""
        self._s = session

    def _protokol(self, protokol_id: str, *, for_share: bool = False) -> RisetProtokolModel:
        """Ambil protokol atau lempar `NotFoundError` (404).

        Args:
            protokol_id: ID protokol riset.
            for_share: Bila benar, baris dikunci `FOR SHARE` agar status protokol tidak
                berubah selama transaksi pembuatan statistik.
        """
        stmt = select(RisetProtokolModel).where(RisetProtokolModel.id == protokol_id)
        if for_share:
            stmt = stmt.with_for_update(read=True)
        rec = self._s.scalar(stmt)
        if rec is None:
            raise NotFoundError(f"Protokol riset '{protokol_id}' tidak ditemukan.")
        return rec

    def create(
        self, protokol_id: str, data: RisetStatistikCreate, *, dibuat_oleh: str
    ) -> RisetStatistikRead:
        """Simpan statistik `DRAF`; protokol harus `TERKUNCI`.

        Raises:
            NotFoundError: Protokol tak ada (404).
            ProtokolBelumTerkunciError: Protokol masih `DRAF` (409 `PROTOKOL_BELUM_TERKUNCI`).
        """
        protokol = self._protokol(protokol_id, for_share=True)
        if protokol.status != StatusProtokol.TERKUNCI.value:
            raise ProtokolBelumTerkunciError(
                f"Protokol riset '{protokol.kode}' versi {protokol.versi} belum terkunci; "
                "statistik hanya dapat dicatat untuk protokol TERKUNCI."
            )
        rec = RisetStatistikModel(
            id=str(uuid.uuid4()),
            protokol_id=protokol.id,
            nama_analisis=data.nama_analisis,
            keluaran=data.keluaran,
            kode_sumber_ref=data.kode_sumber_ref,
            status=StatusStatistik.DRAF.value,
            dibuat_oleh=dibuat_oleh,
            created_at=datetime.now(UTC),
        )
        self._s.add(rec)
        self._s.flush()
        self._s.refresh(rec)
        return _to_read(rec)

    def list_by_protokol(
        self, protokol_id: str, *, status: str | None, limit: int, offset: int
    ) -> tuple[list[RisetStatistikRead], int]:
        """Daftar statistik satu protokol terbaru dulu; `NotFoundError` bila protokol tak ada."""
        self._protokol(protokol_id)
        m = RisetStatistikModel
        conds = [m.protokol_id == protokol_id]
        if status is not None:
            conds.append(m.status == status)
        total = self._s.scalar(select(func.count()).select_from(m).where(*conds)) or 0
        rows = self._s.scalars(
            select(m).where(*conds).order_by(m.created_at.desc(), m.id).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def verifikasi(self, statistik_id: str, *, diverifikasi_oleh: str) -> RisetStatistikRead:
        """Verifikasi statistik; baris dikunci `FOR UPDATE` agar dua verifikasi tak lolos.

        Urutan pemeriksaan: 404, lalu sudah terverifikasi, lalu independensi pemverifikasi.

        Raises:
            NotFoundError: Statistik tak ada (404).
            StatistikSudahTerverifikasiError: Sudah `TERVERIFIKASI` (409).
            PemverifikasiTidakIndependenError: `diverifikasi_oleh` = `dibuat_oleh` (409).
        """
        rec = self._s.get(RisetStatistikModel, statistik_id, with_for_update=True)
        if rec is None:
            raise NotFoundError(f"Statistik riset '{statistik_id}' tidak ditemukan.")
        if rec.status == StatusStatistik.TERVERIFIKASI.value:
            raise StatistikSudahTerverifikasiError(
                f"Statistik riset '{statistik_id}' sudah terverifikasi."
            )
        if rec.dibuat_oleh == diverifikasi_oleh:
            raise PemverifikasiTidakIndependenError(
                "Statistik harus diverifikasi subjek yang berbeda dari pengunggahnya."
            )
        rec.status = StatusStatistik.TERVERIFIKASI.value
        rec.diverifikasi_oleh = diverifikasi_oleh
        rec.diverifikasi_pada = datetime.now(UTC)
        self._s.flush()
        self._s.refresh(rec)
        return _to_read(rec)
