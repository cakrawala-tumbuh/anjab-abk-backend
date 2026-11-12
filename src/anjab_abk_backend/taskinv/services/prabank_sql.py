"""Implementasi `TiPrabankService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import TiCeritaPrabankModel, TiPaparanEventModel, TiRespondenModel
from ..schemas.prabank import (
    CeritaPrabankRead,
    ExposureState,
    JenisPaparan,
    PaparanRead,
    PrabankRead,
    StatusPaparan,
)
from .prabank import CeritaKosongError, CeritaSudahDikunciError


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _cerita_read(rec: TiCeritaPrabankModel) -> CeritaPrabankRead:
    return CeritaPrabankRead(id=rec.id, teks=rec.teks, frozen_at=_aware(rec.frozen_at))


class SqlTiPrabankService:
    """`TiPrabankService` berbasis PostgreSQL, terikat pada satu `Session` per request.

    Pemeriksaan keberadaan responden dilakukan pemanggil (router) lewat
    `TiRespondenService.get`; `status_paparan` satu-satunya method yang juga
    mengecek keberadaan responden sendiri karena dipakai domain lain.
    """

    def __init__(self, session: Session) -> None:
        self._s = session

    def _cerita(self, responden_id: str, *, kunci: bool = False) -> TiCeritaPrabankModel | None:
        stmt = select(TiCeritaPrabankModel).where(TiCeritaPrabankModel.responden_id == responden_id)
        if kunci:
            stmt = stmt.with_for_update()
        return self._s.scalars(stmt).first()

    def _paparan_pertama(self, responden_id: str) -> TiPaparanEventModel | None:
        return self._s.scalars(
            select(TiPaparanEventModel)
            .where(TiPaparanEventModel.responden_id == responden_id)
            .order_by(TiPaparanEventModel.terjadi_pada, TiPaparanEventModel.id)
            .limit(1)
        ).first()

    def simpan_cerita(self, responden_id: str, teks: str) -> CeritaPrabankRead:
        """Simpan (upsert) cerita; baris dikunci `FOR UPDATE` agar tak balapan dengan bekukan.

        Args:
            responden_id: ID responden pemilik cerita.
            teks: Teks cerita (sudah divalidasi panjangnya oleh skema).

        Returns:
            Cerita tersimpan beserta `frozen_at` (selalu null di sini).

        Raises:
            CeritaSudahDikunciError: 409 `CERITA_SUDAH_DIKUNCI` bila sudah beku.
        """
        rec = self._cerita(responden_id, kunci=True)
        hash_baru = hashlib.sha256(teks.encode("utf-8")).hexdigest()
        if rec is None:
            rec = TiCeritaPrabankModel(
                id=str(uuid.uuid4()),
                responden_id=responden_id,
                teks=teks,
                teks_hash=hash_baru,
            )
            self._s.add(rec)
        else:
            if rec.frozen_at is not None:
                raise CeritaSudahDikunciError("Cerita sudah dikunci dan tidak dapat diubah.")
            rec.teks = teks
            rec.teks_hash = hash_baru
        self._s.flush()
        return _cerita_read(rec)

    def bekukan(self, responden_id: str) -> CeritaPrabankRead:
        """Bekukan cerita; panggilan ulang idempoten (waktu beku tidak berubah).

        Raises:
            CeritaKosongError: 422 `CERITA_KOSONG` bila cerita belum ada atau hanya spasi.
        """
        rec = self._cerita(responden_id, kunci=True)
        if rec is None or not rec.teks.strip():
            raise CeritaKosongError(
                "Cerita belum diisi; tulis cerita lebih dulu sebelum dibekukan."
            )
        if rec.frozen_at is None:
            rec.frozen_at = datetime.now(UTC)
            self._s.flush()
        return _cerita_read(rec)

    def catat_paparan(self, responden_id: str, jenis: JenisPaparan) -> PaparanRead:
        """Tambahkan baris log paparan bertimestamp server.

        Status = `LOCKED_PRE_EXPOSURE` bila cerita sudah beku pada atau sebelum saat ini,
        selain itu `EXPOSED`. Cerita yang belum beku tidak memblokir paparan.
        """
        sekarang = datetime.now(UTC)
        rec_cerita = self._cerita(responden_id)
        beku = _aware(rec_cerita.frozen_at) if rec_cerita is not None else None
        status = (
            StatusPaparan.LOCKED_PRE_EXPOSURE
            if beku is not None and beku <= sekarang
            else StatusPaparan.EXPOSED
        )
        ev = TiPaparanEventModel(
            id=str(uuid.uuid4()),
            responden_id=responden_id,
            jenis=jenis.value,
            terjadi_pada=sekarang,
            status_saat_paparan=status.value,
        )
        self._s.add(ev)
        self._s.flush()
        return PaparanRead(id=ev.id, jenis=jenis, terjadi_pada=sekarang, status_saat_paparan=status)

    def baca(self, responden_id: str) -> PrabankRead:
        """Ringkasan cerita + paparan pertama; `exposure_state` dari paparan pertama."""
        rec = self._cerita(responden_id)
        pertama = self._paparan_pertama(responden_id)
        cerita = _cerita_read(rec) if rec is not None else None
        return PrabankRead(
            cerita=cerita,
            frozen_at=cerita.frozen_at if cerita is not None else None,
            first_exposed_at=_aware(pertama.terjadi_pada) if pertama is not None else None,
            exposure_state=(
                ExposureState(pertama.status_saat_paparan)
                if pertama is not None
                else ExposureState.BELUM_TERPAPAR
            ),
        )

    def status_paparan(self, responden_id: str) -> ExposureState | None:
        """Titik baca domain lain: status paparan responden, `None` bila responden tak ada."""
        if self._s.get(TiRespondenModel, responden_id) is None:
            return None
        pertama = self._paparan_pertama(responden_id)
        if pertama is None:
            return ExposureState.BELUM_TERPAPAR
        return ExposureState(pertama.status_saat_paparan)

    def status_paparan_banyak(self, responden_ids: Iterable[str]) -> dict[str, ExposureState]:
        """Status paparan banyak responden dalam SATU kueri (bukan N kueri).

        Args:
            responden_ids: Id `ti_responden` yang ditanyakan; duplikat diabaikan.

        Returns:
            Peta id responden -> status. Id yang bukan responden TI tidak ada di peta;
            responden tanpa log paparan bernilai `BELUM_TERPAPAR`.
        """
        ids = set(responden_ids)
        if not ids:
            return {}
        pertama = (
            select(TiPaparanEventModel.status_saat_paparan)
            .where(TiPaparanEventModel.responden_id == TiRespondenModel.id)
            .order_by(TiPaparanEventModel.terjadi_pada, TiPaparanEventModel.id)
            .limit(1)
            .correlate(TiRespondenModel)
            .scalar_subquery()
        )
        rows = self._s.execute(
            select(TiRespondenModel.id, pertama).where(TiRespondenModel.id.in_(ids))
        ).all()
        return {
            rid: ExposureState(status) if status is not None else ExposureState.BELUM_TERPAPAR
            for rid, status in rows
        }

    def ada_paparan(self, responden_id: str) -> bool:
        """True bila responden punya >= 1 baris log paparan."""
        return self._paparan_pertama(responden_id) is not None
