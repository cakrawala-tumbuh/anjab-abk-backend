"""Implementasi `NarasiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from ...models import (
    NarasiEventModel,
    NarasiKasusModel,
    NarasiSumberModel,
    NarasiVersiModel,
    NarasiVersiSumberModel,
)
from ..schemas.kasus import METADATA_AI_KUNCI, EventKind, RevisionOrigin, StatusNarasi
from ..schemas.mesin import (
    AKTOR_AI_WORKER,
    AktorNarasi,
    KutipanSumber,
    NarasiEventRead,
    NarasiKasusCreate,
    NarasiKasusRead,
    NarasiVersiRead,
)
from .narasi import (
    EVENT_TAHAP_TIM,
    STATUS_HASIL_VERSI,
    TRANSISI_NARASI,
    EventBelumDibukaError,
    TransisiTidakSahError,
    VersiBasiError,
)


def _to_kasus(rec: NarasiKasusModel) -> NarasiKasusRead:
    return NarasiKasusRead.model_validate(rec, from_attributes=True)


def _to_versi(rec: NarasiVersiModel) -> NarasiVersiRead:
    return NarasiVersiRead.model_validate(rec, from_attributes=True)


def _to_event(rec: NarasiEventModel) -> NarasiEventRead:
    return NarasiEventRead.model_validate(rec, from_attributes=True)


class SqlNarasiService:
    """`NarasiService` berbasis PostgreSQL; terikat satu `Session` per request.

    Setiap penulisan mengunci baris kasus (`SELECT ... FOR UPDATE`) sehingga pembacaan
    versi terbaru, pemeriksaan transisi, dan pembaruan status berada dalam satu urutan.
    """

    def __init__(self, session: Session) -> None:
        self._s = session

    def _kunci_kasus(self, narasi_id: str) -> NarasiKasusModel:
        """Ambil kasus dengan kunci tulis; `NotFoundError` bila tak ada."""
        rec = self._s.scalars(
            select(NarasiKasusModel).where(NarasiKasusModel.id == narasi_id).with_for_update()
        ).one_or_none()
        if rec is None:
            raise NotFoundError(f"Kasus narasi '{narasi_id}' tidak ditemukan.")
        return rec

    def _versi_terbaru(self, narasi_id: str) -> NarasiVersiModel | None:
        return self._s.scalars(
            select(NarasiVersiModel)
            .where(NarasiVersiModel.narasi_id == narasi_id)
            .order_by(NarasiVersiModel.revision_no.desc())
            .limit(1)
        ).one_or_none()

    @staticmethod
    def _cek_transisi(dari: str, ke: StatusNarasi) -> None:
        boleh = TRANSISI_NARASI.get(StatusNarasi(dari), frozenset())
        if ke not in boleh:
            raise TransisiTidakSahError(f"Transisi {dari} -> {ke.value} tidak diizinkan.")

    def buat_kasus(self, data: NarasiKasusCreate, aktor: AktorNarasi) -> NarasiKasusRead:
        """Buat kasus berstatus `SOURCE_CHECKED`.

        Raises:
            ConflictError: lingkup kasus yang sama sudah ada (409).
        """
        rec = NarasiKasusModel(
            id=str(uuid.uuid4()),
            **data.model_dump(mode="json"),
            status=StatusNarasi.SOURCE_CHECKED.value,
            dibuat_oleh=aktor.key,
        )
        try:
            with self._s.begin_nested():
                self._s.add(rec)
                self._s.flush()
        except IntegrityError as exc:
            if getattr(exc.orig, "sqlstate", None) != "23505":
                raise
            raise ConflictError("Kasus narasi untuk lingkup ini sudah ada.") from exc
        self._s.refresh(rec)
        return _to_kasus(rec)

    def tambah_versi(
        self,
        narasi_id: str,
        *,
        revision_origin: RevisionOrigin,
        status_hasil: StatusNarasi,
        teks: str | None,
        sumber: list[KutipanSumber],
        supersedes_id: str | None,
        aktor: AktorNarasi,
        ai_run_id: str | None = None,
        output_hash: str | None = None,
        metadata_ai: dict[str, Any] | None = None,
    ) -> NarasiVersiRead:
        """Tambah versi baru, simpan tautan sumber, dan pindahkan status ke `status_hasil`.

        Args:
            narasi_id: Kasus yang diberi versi.
            revision_origin: Asal versi.
            status_hasil: Hasil pembuatan versi (`AI_DRAFT`, `NEED_FACT`, atau `TEAM_REVIEW`);
                menjadi status baru kasus.
            teks: Isi versi; `None` hanya sah untuk `NEED_FACT`.
            sumber: Kutipan sumber; wajib minimal satu bila `teks` berisi.
            supersedes_id: Versi terbaru saat ini (`None` untuk versi pertama).
            aktor: Pelaku (boleh `system:ai-worker`).
            ai_run_id: Run AI penghasil versi, bila ada.
            output_hash: Hash keluaran AI, bila ada.
            metadata_ai: Metadata AI; kunci terbatas pada `METADATA_AI_KUNCI`.

        Returns:
            Versi yang tersimpan, dengan `revision_no` = maks + 1.

        Raises:
            NotFoundError: kasus tak ada.
            VersiBasiError: `supersedes_id` bukan versi terbaru.
            TransisiTidakSahError: status kasus tak boleh pindah ke `status_hasil`.
            ValidationAppError: `teks`/sumber/hash/metadata tidak sah (`NO_SOURCE_NO_FACT`).
        """
        kasus = self._kunci_kasus(narasi_id)
        if status_hasil not in STATUS_HASIL_VERSI:
            raise ValidationAppError(f"status_hasil '{status_hasil.value}' tidak sah untuk versi.")
        terbaru = self._versi_terbaru(narasi_id)
        if supersedes_id != (terbaru.id if terbaru else None):
            raise VersiBasiError("supersedes_id bukan versi terbaru kasus ini.")
        self._cek_transisi(kasus.status, status_hasil)
        if teks is None and status_hasil != StatusNarasi.NEED_FACT:
            raise ValidationAppError("teks kosong hanya sah untuk status_hasil NEED_FACT.")
        if metadata_ai is not None and not set(metadata_ai) <= set(METADATA_AI_KUNCI):
            raise ValidationAppError("metadata_ai memuat kunci di luar daftar yang diizinkan.")
        if teks is not None and not sumber:
            raise ValidationAppError("NO_SOURCE_NO_FACT: versi berteks wajib punya sumber.")
        for k in sumber:
            ref = self._s.get(NarasiSumberModel, k.sumber_id)
            if ref is None:
                raise ValidationAppError(f"Sumber '{k.sumber_id}' tidak ditemukan.")
            if ref.teks_hash != k.source_hash:
                raise ValidationAppError(
                    f"NO_SOURCE_NO_FACT: source_hash sumber '{k.sumber_id}' tidak cocok."
                )
        maks = self._s.scalar(
            select(func.coalesce(func.max(NarasiVersiModel.revision_no), 0)).where(
                NarasiVersiModel.narasi_id == narasi_id
            )
        )
        versi = NarasiVersiModel(
            id=str(uuid.uuid4()),
            narasi_id=narasi_id,
            revision_no=(maks or 0) + 1,
            revision_origin=revision_origin.value,
            status_hasil=status_hasil.value,
            teks=teks,
            supersedes_id=supersedes_id,
            ai_run_id=ai_run_id,
            output_hash=output_hash,
            metadata_ai=metadata_ai,
            dibuat_oleh=aktor.key,
        )
        self._s.add(versi)
        self._s.flush()
        for k in sumber:
            self._s.add(
                NarasiVersiSumberModel(
                    id=str(uuid.uuid4()),
                    narasi_versi_id=versi.id,
                    sumber_id=k.sumber_id,
                    source_span=k.source_span,
                    source_hash=k.source_hash,
                    basis_relation=k.basis_relation.value,
                )
            )
        kasus.status = status_hasil.value
        self._s.flush()
        self._s.refresh(versi)
        return _to_versi(versi)

    def catat_event(
        self,
        narasi_id: str,
        narasi_versi_id: str | None,
        event_kind: EventKind,
        aktor: AktorNarasi,
        catatan: str | None,
    ) -> NarasiEventRead:
        """Catat tindakan manusia tahap Tim dan pindahkan status kasus.

        Args:
            narasi_id: Kasus yang ditinjau.
            narasi_versi_id: Versi terbaru kasus (`None` bila kasus belum punya versi).
            event_kind: Jenis tindakan; hanya `EVENT_TAHAP_TIM` yang dibuka.
            aktor: Pelaku manusia; `system:ai-worker` ditolak.
            catatan: Catatan bebas.

        Returns:
            Event yang tersimpan.

        Raises:
            ForbiddenError: aktor `system:ai-worker` (403), tanpa baris.
            NotFoundError: kasus tak ada.
            EventBelumDibukaError: `event_kind` di luar tahap Tim.
            VersiBasiError: `narasi_versi_id` bukan versi terbaru.
            TransisiTidakSahError: transisi di luar `TRANSISI_NARASI`, atau kasus berstatus
                `TEAM_VERIFIED` (kembali ke `TEAM_REVIEW` hanya lewat versi baru).
            ValidationAppError: tujuan `TEAM_REVIEW`/`TEAM_VERIFIED`, versi terbaru tanpa teks.
        """
        if aktor.key == AKTOR_AI_WORKER:
            raise ForbiddenError("Proses AI tidak boleh mencatat event tinjauan.")
        if event_kind not in EVENT_TAHAP_TIM:
            raise EventBelumDibukaError(f"Event {event_kind.value} belum dibuka.")
        kasus = self._kunci_kasus(narasi_id)
        terbaru = self._versi_terbaru(narasi_id)
        if narasi_versi_id != (terbaru.id if terbaru else None):
            raise VersiBasiError("narasi_versi_id bukan versi terbaru kasus ini.")
        if kasus.status == StatusNarasi.TEAM_VERIFIED.value:
            raise TransisiTidakSahError(
                "Kasus TEAM_VERIFIED hanya kembali ke TEAM_REVIEW lewat versi baru."
            )
        ke = EVENT_TAHAP_TIM[event_kind]
        self._cek_transisi(kasus.status, ke)
        if ke in (StatusNarasi.TEAM_REVIEW, StatusNarasi.TEAM_VERIFIED) and (
            terbaru is None or terbaru.teks is None
        ):
            raise ValidationAppError("Versi terbaru tanpa teks tidak dapat ditinjau tim.")
        event = NarasiEventModel(
            id=str(uuid.uuid4()),
            narasi_id=narasi_id,
            narasi_versi_id=narasi_versi_id,
            actor_key=aktor.key,
            actor_role=aktor.role,
            event_kind=event_kind.value,
            dari_status=kasus.status,
            ke_status=ke.value,
            event_notes=catatan,
        )
        self._s.add(event)
        kasus.status = ke.value
        self._s.flush()
        self._s.refresh(event)
        return _to_event(event)
