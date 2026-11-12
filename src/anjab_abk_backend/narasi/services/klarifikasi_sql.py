"""Implementasi `KlarifikasiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

Tiap aksi menulis satu baris `narasi_klarifikasi_event` dalam transaksi yang sama dengan
perubahan proyeksi `narasi_klarifikasi`. Baris induk dikunci `FOR UPDATE` pada aksi ubah
agar dua keputusan bersamaan tidak saling menimpa.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from psycopg.errors import UniqueViolation
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import NotFoundError
from ...models import NarasiKasusModel, NarasiKlarifikasiEventModel, NarasiKlarifikasiModel
from ..schemas.klarifikasi import (
    AksiKlarifikasi,
    BatalkanKlarifikasi,
    Disposition,
    JawabanKlarifikasi,
    KeputusanReviewer,
    KlarifikasiCreate,
    KlarifikasiDetail,
    KlarifikasiEventRead,
    KlarifikasiRead,
    PersetujuanKlarifikasi,
    ReviewerApproval,
)
from .klarifikasi import (
    KlarifikasiBelumDisetujuiError,
    KlarifikasiGandaError,
    KlarifikasiTidakTerbukaError,
    PersetujuanSudahAdaError,
    ReviewerTidakIndependenError,
)


def _aware(dt: datetime) -> datetime:
    """Pastikan datetime ber-zona waktu (UTC) sebelum masuk skema respons."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def _to_read(rec: NarasiKlarifikasiModel) -> KlarifikasiRead:
    """Petakan baris ORM ke representasi respons (tanpa riwayat)."""
    return KlarifikasiRead(
        id=rec.id,
        narasi_id=rec.narasi_id,
        claim_id=rec.claim_id,
        source_ids_checked=list(rec.source_ids_checked),
        materiality_reason=rec.materiality_reason,
        alternative_hypothesis=rec.alternative_hypothesis,
        intended_decision=rec.intended_decision,
        recipient_role=rec.recipient_role,
        periode=rec.periode,
        exposure=rec.exposure,
        due_trigger=rec.due_trigger,
        question_text=rec.question_text,
        reviewer_approval=ReviewerApproval(rec.reviewer_approval),
        response_ref=rec.response_ref,
        jawaban_mentah=rec.jawaban_mentah,
        disposition=Disposition(rec.disposition),
        ai_usulan_id=rec.ai_usulan_id,
        dibuat_oleh=rec.dibuat_oleh,
        created_at=_aware(rec.created_at),
        updated_at=_aware(rec.updated_at),
    )


class SqlKlarifikasiService:
    """`KlarifikasiService` berbasis PostgreSQL; terikat satu `Session` per request."""

    def __init__(self, session: Session) -> None:
        """Simpan sesi per-request yang dipakai seluruh operasi."""
        self._s = session

    def _muat(self, klarifikasi_id: str, *, kunci: bool = False) -> NarasiKlarifikasiModel:
        """Ambil baris induk atau lempar `NotFoundError` (404).

        Args:
            klarifikasi_id: Question_ID.
            kunci: Bila benar, baris dikunci `FOR UPDATE` selama transaksi.
        """
        stmt = select(NarasiKlarifikasiModel).where(NarasiKlarifikasiModel.id == klarifikasi_id)
        if kunci:
            stmt = stmt.with_for_update()
        rec = self._s.scalar(stmt)
        if rec is None:
            raise NotFoundError(f"Klarifikasi '{klarifikasi_id}' tidak ditemukan.")
        return rec

    def _event(
        self, rec: NarasiKlarifikasiModel, aksi: AksiKlarifikasi, actor: str, catatan: str | None
    ) -> None:
        """Tambah satu baris riwayat untuk `rec`; waktu dari server aplikasi (UTC)."""
        self._s.add(
            NarasiKlarifikasiEventModel(
                id=str(uuid.uuid4()),
                klarifikasi_id=rec.id,
                aksi=aksi.value,
                actor_key=actor,
                catatan=catatan,
                terjadi_pada=datetime.now(UTC),
            )
        )

    def _detail(self, rec: NarasiKlarifikasiModel) -> KlarifikasiDetail:
        """Flush perubahan lalu rakit `KlarifikasiDetail` dengan riwayat terlama dulu."""
        self._s.flush()
        self._s.refresh(rec)
        m = NarasiKlarifikasiEventModel
        rows = self._s.scalars(
            select(m).where(m.klarifikasi_id == rec.id).order_by(m.terjadi_pada, m.id)
        ).all()
        riwayat = [
            KlarifikasiEventRead(
                id=r.id,
                klarifikasi_id=r.klarifikasi_id,
                aksi=AksiKlarifikasi(r.aksi),
                actor_key=r.actor_key,
                catatan=r.catatan,
                terjadi_pada=_aware(r.terjadi_pada),
            )
            for r in rows
        ]
        return KlarifikasiDetail(**_to_read(rec).model_dump(), riwayat=riwayat)

    def create(self, data: KlarifikasiCreate, *, dibuat_oleh: str) -> KlarifikasiDetail:
        """Simpan pertanyaan `MENUNGGU`/`TERBUKA` + event `DIBUAT`.

        Raises:
            NotFoundError: Kasus narasi tak ada (404).
            KlarifikasiGandaError: Sudah ada klarifikasi `TERBUKA` untuk (narasi, klaim) itu.
        """
        if self._s.get(NarasiKasusModel, data.narasi_id) is None:
            raise NotFoundError(f"Kasus narasi '{data.narasi_id}' tidak ditemukan.")
        m = NarasiKlarifikasiModel
        ganda = self._s.scalar(
            select(func.count())
            .select_from(m)
            .where(
                m.narasi_id == data.narasi_id,
                m.claim_id == data.claim_id,
                m.disposition == Disposition.TERBUKA.value,
            )
        )
        if ganda:
            raise KlarifikasiGandaError(
                f"Sudah ada klarifikasi terbuka untuk klaim '{data.claim_id}' pada kasus ini."
            )
        sekarang = datetime.now(UTC)
        rec = m(
            id=str(uuid.uuid4()),
            narasi_id=data.narasi_id,
            claim_id=data.claim_id,
            source_ids_checked=list(data.source_ids_checked),
            materiality_reason=data.materiality_reason,
            alternative_hypothesis=data.alternative_hypothesis,
            intended_decision=data.intended_decision,
            recipient_role=data.recipient_role,
            periode=data.periode,
            exposure=data.exposure.value,
            due_trigger=data.due_trigger,
            question_text=data.question_text,
            reviewer_approval=ReviewerApproval.MENUNGGU.value,
            disposition=Disposition.TERBUKA.value,
            dibuat_oleh=dibuat_oleh,
            created_at=sekarang,
            updated_at=sekarang,
        )
        try:
            with self._s.begin_nested():
                self._s.add(rec)
                self._s.flush()
        except IntegrityError as exc:
            if isinstance(exc.orig, UniqueViolation):
                raise KlarifikasiGandaError(
                    f"Sudah ada klarifikasi terbuka untuk klaim '{data.claim_id}' pada kasus ini."
                ) from exc
            raise
        self._event(rec, AksiKlarifikasi.DIBUAT, dibuat_oleh, None)
        return self._detail(rec)

    def get(self, klarifikasi_id: str) -> KlarifikasiDetail:
        """Ambil satu pertanyaan beserta `riwayat`; `NotFoundError` bila tak ada."""
        return self._detail(self._muat(klarifikasi_id))

    def daftar(
        self,
        *,
        narasi_id: str | None,
        disposition: Disposition | None,
        limit: int,
        offset: int,
    ) -> tuple[list[KlarifikasiRead], int]:
        """Daftar pertanyaan, terbaru dulu, dengan filter `narasi_id`/`disposition`."""
        m = NarasiKlarifikasiModel
        conds = []
        if narasi_id is not None:
            conds.append(m.narasi_id == narasi_id)
        if disposition is not None:
            conds.append(m.disposition == disposition.value)
        total = self._s.scalar(select(func.count()).select_from(m).where(*conds)) or 0
        rows = self._s.scalars(
            select(m).where(*conds).order_by(m.created_at.desc(), m.id).limit(limit).offset(offset)
        ).all()
        return [_to_read(r) for r in rows], total

    def putuskan(
        self, klarifikasi_id: str, data: PersetujuanKlarifikasi, *, reviewer: str
    ) -> KlarifikasiDetail:
        """Setujui/tolak pertanyaan `TERBUKA` yang `MENUNGGU`.

        Raises:
            NotFoundError: Tak ada (404).
            KlarifikasiTidakTerbukaError: Bukan `TERBUKA` (409).
            PersetujuanSudahAdaError: Sudah diputus (409).
            ReviewerTidakIndependenError: `reviewer` = pembuat (409).
        """
        rec = self._muat(klarifikasi_id, kunci=True)
        if rec.disposition != Disposition.TERBUKA.value:
            raise KlarifikasiTidakTerbukaError(Disposition(rec.disposition))
        if rec.reviewer_approval != ReviewerApproval.MENUNGGU.value:
            raise PersetujuanSudahAdaError(
                f"Pertanyaan sudah diputus ({rec.reviewer_approval}); "
                "keputusan tidak dapat diulang."
            )
        if reviewer == rec.dibuat_oleh:
            raise ReviewerTidakIndependenError(
                "Reviewer harus orang lain, bukan pembuat pertanyaan."
            )
        setuju = data.keputusan is KeputusanReviewer.SETUJU
        rec.reviewer_approval = (
            ReviewerApproval.DISETUJUI if setuju else ReviewerApproval.DITOLAK
        ).value
        self._event(
            rec,
            AksiKlarifikasi.DISETUJUI if setuju else AksiKlarifikasi.DITOLAK,
            reviewer,
            data.catatan,
        )
        return self._detail(rec)

    def catat_jawaban(
        self, klarifikasi_id: str, data: JawabanKlarifikasi, *, pencatat: str
    ) -> KlarifikasiDetail:
        """Catat jawaban mentah; disposisi menjadi `TERJAWAB`.

        Raises:
            NotFoundError: Tak ada (404).
            KlarifikasiTidakTerbukaError: Sudah `TERJAWAB`/`DIBATALKAN` (409).
            KlarifikasiBelumDisetujuiError: Belum `DISETUJUI` (409).
        """
        rec = self._muat(klarifikasi_id, kunci=True)
        if rec.disposition != Disposition.TERBUKA.value:
            raise KlarifikasiTidakTerbukaError(Disposition(rec.disposition))
        if rec.reviewer_approval != ReviewerApproval.DISETUJUI.value:
            raise KlarifikasiBelumDisetujuiError(
                "Jawaban hanya dapat dicatat setelah pertanyaan disetujui reviewer."
            )
        rec.response_ref = data.response_ref
        rec.jawaban_mentah = data.jawaban_mentah
        rec.disposition = Disposition.TERJAWAB.value
        self._event(rec, AksiKlarifikasi.JAWABAN_DICATAT, pencatat, data.response_ref)
        return self._detail(rec)

    def batalkan(
        self, klarifikasi_id: str, data: BatalkanKlarifikasi, *, pembatal: str
    ) -> KlarifikasiDetail:
        """Batalkan pertanyaan `TERBUKA`; disposisi menjadi `DIBATALKAN`.

        Raises:
            NotFoundError: Tak ada (404).
            KlarifikasiTidakTerbukaError: Bukan `TERBUKA` (409).
        """
        rec = self._muat(klarifikasi_id, kunci=True)
        if rec.disposition != Disposition.TERBUKA.value:
            raise KlarifikasiTidakTerbukaError(Disposition(rec.disposition))
        rec.disposition = Disposition.DIBATALKAN.value
        self._event(rec, AksiKlarifikasi.DIBATALKAN, pembatal, data.catatan)
        return self._detail(rec)
