"""Implementasi `RisetSignoffService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, date, datetime

from psycopg.errors import UniqueViolation
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..errors import NotFoundError, ValidationAppError
from ..models import RisetProtokolModel, RisetProtokolSignoffModel
from ..schemas.riset_protokol import StatusProtokol
from ..schemas.riset_signoff import MAGIC_PDF, SignoffRead
from .riset_signoff import (
    LampiranBukanPdfError,
    LampiranSignoff,
    LampiranTerlaluBesarError,
    SignoffSudahAdaError,
    SignoffTakAdaError,
)
from .riset_statistik import ProtokolBelumTerkunciError


def _aware(dt: datetime) -> datetime:
    """Pastikan datetime ber-zona waktu (UTC)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_read(rec: RisetProtokolSignoffModel) -> SignoffRead:
    """Petakan baris ORM ke metadata (tanpa byte lampiran)."""
    return SignoffRead(
        id=rec.id,
        protokol_id=rec.protokol_id,
        pi_nama=rec.pi_nama,
        tanggal_persetujuan_etik=rec.tanggal_persetujuan_etik,
        nomor_persetujuan_etik=rec.nomor_persetujuan_etik,
        lampiran_nama=rec.lampiran_nama,
        lampiran_ukuran=rec.lampiran_ukuran,
        lampiran_sha256=rec.lampiran_sha256,
        dicatat_oleh=rec.dicatat_oleh,
        created_at=_aware(rec.created_at),
    )


class SqlRisetSignoffService:
    """`RisetSignoffService` berbasis PostgreSQL; terikat satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        """Simpan sesi per-request."""
        self._s = session

    def _protokol(self, protokol_id: str, *, share: bool = False) -> RisetProtokolModel:
        """Ambil protokol (opsional `FOR SHARE`); `NotFoundError` bila tak ada."""
        if share:
            rec = self._s.scalar(
                select(RisetProtokolModel)
                .where(RisetProtokolModel.id == protokol_id)
                .with_for_update(read=True)
            )
        else:
            rec = self._s.get(RisetProtokolModel, protokol_id)
        if rec is None:
            raise NotFoundError(f"Protokol riset '{protokol_id}' tidak ditemukan.")
        return rec

    def _baris(self, protokol_id: str) -> RisetProtokolSignoffModel:
        """Ambil baris sign-off protokol; 404 protokol atau `SignoffTakAdaError`."""
        self._protokol(protokol_id)
        rec = self._s.scalar(
            select(RisetProtokolSignoffModel).where(
                RisetProtokolSignoffModel.protokol_id == protokol_id
            )
        )
        if rec is None:
            raise SignoffTakAdaError(f"Protokol '{protokol_id}' belum punya sign-off PI/etik.")
        return rec

    def create(
        self,
        protokol_id: str,
        *,
        pi_nama: str,
        tanggal_persetujuan_etik: date,
        nomor_persetujuan_etik: str | None,
        lampiran_nama: str,
        content_type: str | None,
        isi: bytes,
        maks_bytes: int,
        dicatat_oleh: str,
    ) -> SignoffRead:
        """Catat sign-off; urutan cek: 404, terkunci, sudah ada, PDF, ukuran, tanggal.

        Flush berjalan dalam SAVEPOINT; hanya `UniqueViolation` (dua unggahan bersamaan)
        dipetakan ke 409 `SIGNOFF_SUDAH_ADA`.

        Raises:
            NotFoundError: Protokol tak ada (404).
            ProtokolBelumTerkunciError: Protokol `DRAF` (409).
            SignoffSudahAdaError: Sudah ada sign-off (409).
            LampiranBukanPdfError: Content-type bukan PDF atau byte awal bukan `%PDF-`.
            LampiranTerlaluBesarError: `len(isi)` melebihi `maks_bytes`.
            ValidationAppError: Tanggal persetujuan di masa depan.
        """
        protokol = self._protokol(protokol_id, share=True)
        if protokol.status != StatusProtokol.TERKUNCI.value:
            raise ProtokolBelumTerkunciError(
                "Sign-off hanya untuk protokol berstatus TERKUNCI; kunci protokol lebih dulu."
            )
        ada = self._s.scalar(
            select(RisetProtokolSignoffModel.id).where(
                RisetProtokolSignoffModel.protokol_id == protokol_id
            )
        )
        if ada is not None:
            raise SignoffSudahAdaError("Protokol ini sudah punya sign-off PI/etik.")
        tipe = (content_type or "").split(";")[0].strip().lower()
        if tipe != "application/pdf" or not isi.startswith(MAGIC_PDF):
            raise LampiranBukanPdfError("Lampiran harus berkas PDF (application/pdf).")
        if len(isi) > maks_bytes:
            raise LampiranTerlaluBesarError(f"Lampiran melebihi batas {maks_bytes} byte.")
        if tanggal_persetujuan_etik > datetime.now(UTC).date():
            raise ValidationAppError("tanggal_persetujuan_etik tidak boleh di masa depan.")
        rec = RisetProtokolSignoffModel(
            id=str(uuid.uuid4()),
            protokol_id=protokol_id,
            pi_nama=pi_nama,
            tanggal_persetujuan_etik=tanggal_persetujuan_etik,
            nomor_persetujuan_etik=nomor_persetujuan_etik,
            lampiran_pdf=isi,
            lampiran_nama=lampiran_nama[:255],
            lampiran_ukuran=len(isi),
            lampiran_sha256=hashlib.sha256(isi).hexdigest(),
            dicatat_oleh=dicatat_oleh,
            created_at=datetime.now(UTC),
        )
        try:
            with self._s.begin_nested():
                self._s.add(rec)
                self._s.flush()
        except IntegrityError as exc:
            if isinstance(exc.orig, UniqueViolation):
                raise SignoffSudahAdaError("Protokol ini sudah punya sign-off PI/etik.") from exc
            raise
        self._s.refresh(rec)
        return _to_read(rec)

    def get(self, protokol_id: str) -> SignoffRead:
        """Metadata sign-off; 404 protokol tak ada, 404 `SIGNOFF_TAK_ADA` bila belum ada."""
        return _to_read(self._baris(protokol_id))

    def lampiran(self, protokol_id: str) -> LampiranSignoff:
        """Byte PDF sign-off beserta nama dan SHA-256 (kolom `deferred` dimuat saat diakses)."""
        rec = self._baris(protokol_id)
        return LampiranSignoff(
            nama=rec.lampiran_nama, isi=bytes(rec.lampiran_pdf), sha256=rec.lampiran_sha256
        )


def signoff_ada(session: Session, protokol_id: str) -> bool:
    """True bila protokol sudah punya baris sign-off (dipakai `ProtokolRead` dan gerbang P08)."""
    return (
        session.scalar(
            select(RisetProtokolSignoffModel.id).where(
                RisetProtokolSignoffModel.protokol_id == protokol_id
            )
        )
        is not None
    )
