"""Implementasi `NarasiMetrikService` di atas PostgreSQL; seluruh agregasi dikerjakan di SQL."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import case, exists, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ...errors import NotFoundError
from ...models import (
    NarasiEventModel,
    NarasiKasusModel,
    NarasiMenitAktifModel,
    NarasiVersiModel,
    NarasiVersiSumberModel,
)
from ..schemas.kasus import EventKind, NarrativeKind
from ..schemas.metrik import MetrikNarasiRead
from .metrik import periksa_rentang, potong_ke_menit

_KEPUTUSAN = (
    EventKind.TEAM_APPROVE.value,
    EventKind.TEAM_REVISE.value,
    EventKind.TEAM_REJECT.value,
    EventKind.NEED_SOURCE.value,
)
"""Jenis event yang dihitung sebagai keputusan Tim."""


def _rasio(bagian: int, penyebut: int) -> float | None:
    """Bagi dan bulatkan 4 angka; None bila penyebut 0 (bukan 0)."""
    if penyebut == 0:
        return None
    return round(bagian / penyebut, 4)


class SqlNarasiMetrikService:
    """`NarasiMetrikService` PostgreSQL; sesi dimiliki dependency per-request."""

    def __init__(self, session: Session) -> None:
        """Simpan sesi SQLAlchemy yang dipakai bersama seluruh seam request ini."""
        self._s = session

    def catat_menit_aktif(
        self, narasi_id: str, actor_key: str, sekarang: datetime | None = None
    ) -> None:
        """Sisipkan satu baris menit aktif dengan `ON CONFLICT DO NOTHING`.

        Menit dipotong server dari `sekarang` (bawaan jam UTC server); klien tak mengirim waktu.
        """
        if self._s.get(NarasiKasusModel, narasi_id) is None:
            raise NotFoundError(f"Kasus narasi '{narasi_id}' tidak ditemukan.")
        menit = potong_ke_menit(sekarang or datetime.now(UTC))
        stmt = (
            pg_insert(NarasiMenitAktifModel)
            .values(id=str(uuid.uuid4()), narasi_id=narasi_id, actor_key=actor_key, menit=menit)
            .on_conflict_do_nothing(constraint="uq_narasi_menit_aktif_narasi_actor_menit")
        )
        self._s.execute(stmt)

    def hitung(
        self, dari: date, sampai: date, narrative_kind: NarrativeKind | None = None
    ) -> MetrikNarasiRead:
        """Hitung seluruh metrik dengan empat kueri agregat (keputusan, versi, menit, median)."""
        periksa_rentang(dari, sampai)
        awal = datetime.combine(dari, time.min, tzinfo=UTC)
        akhir = datetime.combine(sampai + timedelta(days=1), time.min, tzinfo=UTC)
        jenis = narrative_kind.value if narrative_kind is not None else None

        def _saring(stmt, model, kolom_waktu, kolom_kasus):
            """Batasi `stmt` (dari `model`) ke rentang waktu dan, bila ada, jenis narasi."""
            stmt = stmt.select_from(model).where(kolom_waktu >= awal, kolom_waktu < akhir)
            if jenis is not None:
                stmt = stmt.join(NarasiKasusModel, NarasiKasusModel.id == kolom_kasus).where(
                    NarasiKasusModel.narrative_kind == jenis
                )
            return stmt

        e = NarasiEventModel
        keputusan = self._s.execute(
            _saring(
                select(
                    func.count(),
                    func.count().filter(e.event_kind == EventKind.TEAM_REVISE.value),
                    func.count().filter(e.event_kind == EventKind.TEAM_REJECT.value),
                ).where(e.event_kind.in_(_KEPUTUSAN)),
                e,
                e.event_at,
                e.narasi_id,
            )
        ).one()
        total_keputusan, n_revisi, n_tolak = (int(x) for x in keputusan)

        v = NarasiVersiModel
        punya_sumber = exists().where(NarasiVersiSumberModel.narasi_versi_id == v.id)
        versi = self._s.execute(
            _saring(
                select(
                    func.count(),
                    func.coalesce(func.sum(case((punya_sumber, 1), else_=0)), 0),
                ),
                v,
                v.created_at,
                v.narasi_id,
            )
        ).one()
        n_versi, n_bersumber = int(versi[0]), int(versi[1])

        m = NarasiMenitAktifModel
        per_kasus = _saring(
            select(m.narasi_id, func.count().label("n")).group_by(m.narasi_id),
            m,
            m.menit,
            m.narasi_id,
        ).subquery()
        menit = self._s.execute(
            select(
                func.coalesce(func.sum(per_kasus.c.n), 0),
                func.percentile_cont(0.5).within_group(per_kasus.c.n),
            )
        ).one()
        median = menit[1]
        return MetrikNarasiRead(
            jumlah_keputusan=total_keputusan,
            correction_rate=_rasio(n_revisi, total_keputusan),
            rejection_rate=_rasio(n_tolak, total_keputusan),
            source_coverage=_rasio(n_bersumber, n_versi),
            menit_aktif_total=int(menit[0]),
            menit_aktif_median_per_kasus=round(float(median), 4) if median is not None else None,
        )
