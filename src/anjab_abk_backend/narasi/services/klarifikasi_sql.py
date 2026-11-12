"""Implementasi `KlarifikasiService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron).

Tiap aksi menulis satu baris `narasi_klarifikasi_event` dalam transaksi yang sama dengan
perubahan proyeksi `narasi_klarifikasi`. Baris induk dikunci `FOR UPDATE` pada aksi ubah
agar dua keputusan bersamaan tidak saling menimpa.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from psycopg.errors import UniqueViolation
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...errors import NotFoundError, ValidationAppError
from ...models import (
    AiRunModel,
    AiUsulanModel,
    AiUsulanPutusanModel,
    NarasiKasusModel,
    NarasiKlarifikasiEventModel,
    NarasiKlarifikasiModel,
)
from ...schemas.ai_usulan import PutusanUsulan, SasaranUsulan
from ..schemas.klarifikasi import (
    AksiKlarifikasi,
    BatalkanKlarifikasi,
    Disposition,
    JawabanKlarifikasi,
    KeputusanReviewer,
    KlarifikasiCreate,
    KlarifikasiDariUsulan,
    KlarifikasiDetail,
    KlarifikasiEventRead,
    KlarifikasiRead,
    PersetujuanKlarifikasi,
    ReviewerApproval,
)
from .klarifikasi import (
    IsianUsulanKurangError,
    KlarifikasiBelumDisetujuiError,
    KlarifikasiGandaError,
    KlarifikasiTidakTerbukaError,
    PeriodeTakAdaError,
    PersetujuanSudahAdaError,
    ReviewerTidakIndependenError,
    UsulanBelumDiterimaError,
    UsulanBukanP04Error,
    UsulanSudahDiterapkanError,
    UsulanTidakMaterialError,
)

KODE_FUNGSI_P04 = "P04"
"""Fungsi AI sumber penerapan; literal agar paket `narasi` tidak mengimpor paket `ai`."""

_UQ_USULAN = "uq_narasi_klarifikasi_ai_usulan"
"""Nama constraint UNIQUE `ai_usulan_id` (membedakannya dari indeks parsial klaim terbuka)."""

ALTERNATIF_KOSONG = "Tidak ada alternatif yang diusulkan P04."
"""Isi `alternative_hypothesis` bila `alternatives` usulan kosong (kolom wajib berisi)."""


def _teks_alternatif(alternatives: Any) -> str:
    """Gabungkan `alternatives` P04 menjadi satu butir per baris diawali `- `.

    Args:
        alternatives: Nilai `isi.alternatives` (daftar string; selain itu dianggap kosong).

    Returns:
        Teks bertingkat butir, atau `ALTERNATIF_KOSONG` bila tak ada butir berisi.
    """
    butir = (
        [a.strip() for a in alternatives if isinstance(a, str) and a.strip()]
        if isinstance(alternatives, list)
        else []
    )
    return "\n".join(f"- {b}" for b in butir) if butir else ALTERNATIF_KOSONG


def _teks_atau_none(nilai: Any) -> str | None:
    """Kembalikan `nilai` bila string berisi (bukan spasi saja), selain itu `None`."""
    return nilai if isinstance(nilai, str) and nilai.strip() else None


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
        return self._simpan(data, dibuat_oleh=dibuat_oleh, ai_usulan_id=None, catatan=None)

    def _simpan(
        self,
        data: KlarifikasiCreate,
        *,
        dibuat_oleh: str,
        ai_usulan_id: str | None,
        catatan: str | None,
    ) -> KlarifikasiDetail:
        """Tulis baris register baru + event `DIBUAT` (dipakai `create` dan `dari_usulan`).

        Args:
            data: Isian tervalidasi.
            dibuat_oleh: Subjek token pembuat.
            ai_usulan_id: Usulan asal (None untuk pembuatan manual).
            catatan: Catatan event `DIBUAT`.

        Raises:
            NotFoundError: Kasus narasi tak ada (404).
            KlarifikasiGandaError: Sudah ada klarifikasi `TERBUKA` untuk (narasi, klaim) itu.
            UsulanSudahDiterapkanError: Bentrok UNIQUE `ai_usulan_id` (permintaan bersamaan).
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
            ai_usulan_id=ai_usulan_id,
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
                if getattr(exc.orig.diag, "constraint_name", None) == _UQ_USULAN:
                    raise UsulanSudahDiterapkanError(None) from exc
                raise KlarifikasiGandaError(
                    f"Sudah ada klarifikasi terbuka untuk klaim '{data.claim_id}' pada kasus ini."
                ) from exc
            raise
        self._event(rec, AksiKlarifikasi.DIBUAT, dibuat_oleh, catatan)
        return self._detail(rec)

    def dari_usulan(
        self, ai_usulan_id: str, data: KlarifikasiDariUsulan, *, dibuat_oleh: str
    ) -> KlarifikasiDetail:
        """Terapkan usulan P04 yang diterima reviewer menjadi SATU baris register.

        Satu transaksi: baris `ai_usulan` dibaca `FOR SHARE`, putusan terakhir (urut
        `created_at` lalu `id`) menentukan penerimaan. Pemetaan tetap: `one_neutral_question`
        -> `question_text`; `materiality_rationale` -> `materiality_reason`; `alternatives` ->
        `alternative_hypothesis` (satu butir per baris diawali `- `); `preferred_role` ->
        `recipient_role`; `why_ask` -> `intended_decision` bila body tak mengisinya;
        `sumber_ids` -> `source_ids_checked`; `sasaran_id` -> `narasi_id`; `periode` dari
        `parameter` run usulan (cadangan: periode kasus sasaran, yang memang nilai parameter
        P04). Baris dibuat `MENUNGGU`/`TERBUKA` dengan event `DIBUAT` bercatatan
        `dari usulan P04 <id>`; usulan dan putusannya tidak diubah.

        Args:
            ai_usulan_id: Id usulan P04.
            data: Isian dari klien (claim, pemicu, paparan, keputusan opsional).
            dibuat_oleh: Subjek token pembuat.

        Returns:
            Detail baris register baru.

        Raises:
            NotFoundError: Usulan tak ada, atau kasus sasaran tak ada (404).
            UsulanBukanP04Error: Fungsi bukan P04 / sasaran bukan `NARASI_KASUS` (422).
            UsulanBelumDiterimaError: Tanpa putusan atau putusan terakhir `REJECT` (409).
            UsulanTidakMaterialError: `isi.material` false atau pertanyaan kosong (422).
            UsulanSudahDiterapkanError: Usulan sudah menjadi klarifikasi (409).
            PeriodeTakAdaError: Periode tak terbaca (422).
            IsianUsulanKurangError: `preferred_role` kosong, atau `why_ask` kosong tanpa
                `intended_decision` di body (422).
            KlarifikasiGandaError: Sudah ada `TERBUKA` untuk klaim itu (409).
            ValidationAppError: Hasil pemetaan tak lolos `KlarifikasiCreate` (422).
        """
        usulan = self._s.scalar(
            select(AiUsulanModel).where(AiUsulanModel.id == ai_usulan_id).with_for_update(read=True)
        )
        if usulan is None:
            raise NotFoundError(f"Usulan AI '{ai_usulan_id}' tidak ditemukan.")
        if (
            usulan.fungsi != KODE_FUNGSI_P04
            or usulan.sasaran_jenis != SasaranUsulan.NARASI_KASUS.value
        ):
            raise UsulanBukanP04Error("Usulan bukan usulan P04 atas kasus narasi.")
        P = AiUsulanPutusanModel
        putusan = self._s.scalar(
            select(P.putusan)
            .where(P.usulan_id == ai_usulan_id)
            .order_by(P.created_at.desc(), P.id.desc())
            .limit(1)
        )
        if putusan not in (PutusanUsulan.APPROVE.value, PutusanUsulan.REVISE.value):
            raise UsulanBelumDiterimaError("Usulan AI ini belum diterima reviewer.")
        isi = usulan.isi or {}
        pertanyaan = _teks_atau_none(isi.get("one_neutral_question"))
        if isi.get("material") is not True or pertanyaan is None:
            raise UsulanTidakMaterialError("Usulan P04 tidak material atau tanpa pertanyaan.")
        ada = self._s.scalar(
            select(NarasiKlarifikasiModel.id).where(
                NarasiKlarifikasiModel.ai_usulan_id == ai_usulan_id
            )
        )
        if ada is not None:
            raise UsulanSudahDiterapkanError(ada)
        periode = self._periode(usulan)
        peran = _teks_atau_none(isi.get("preferred_role"))
        keputusan = _teks_atau_none(data.intended_decision) or _teks_atau_none(isi.get("why_ask"))
        if peran is None or keputusan is None:
            raise IsianUsulanKurangError(
                "Usulan P04 tanpa preferred_role, atau tanpa why_ask dan intended_decision."
            )
        try:
            baru = KlarifikasiCreate(
                narasi_id=usulan.sasaran_id,
                claim_id=data.claim_id,
                source_ids_checked=list(usulan.sumber_ids),
                materiality_reason=str(isi.get("materiality_rationale") or ""),
                alternative_hypothesis=_teks_alternatif(isi.get("alternatives")),
                intended_decision=keputusan,
                recipient_role=peran,
                periode=periode,
                exposure=data.exposure,
                due_trigger=data.due_trigger,
                question_text=pertanyaan,
            )
        except ValidationError as exc:
            salah = sorted({str(e["loc"][0]) for e in exc.errors() if e["loc"]})
            raise ValidationAppError(
                "Isian usulan P04 tidak sah untuk register: " + ", ".join(salah) + "."
            ) from exc
        return self._simpan(
            baru,
            dibuat_oleh=dibuat_oleh,
            ai_usulan_id=ai_usulan_id,
            catatan=f"dari usulan P04 {ai_usulan_id}",
        )

    def _periode(self, usulan: AiUsulanModel) -> str:
        """Baca periode dari `parameter` run usulan; cadangan periode kasus sasarannya.

        `ai_run.masukan` dikosongkan saat run ditutup (kecuali `AI_SIMPAN_MASUKAN`), sedangkan
        parameter P04 selalu `periode` kasus apa adanya, sehingga kasus adalah sumber setara.

        Raises:
            PeriodeTakAdaError: Keduanya tak menghasilkan teks berisi (422).
        """
        run = self._s.get(AiRunModel, usulan.ai_run_id)
        parameter = (run.masukan or {}).get("parameter") if run is not None else None
        periode = _teks_atau_none((parameter or {}).get("periode"))
        if periode is None:
            kasus = self._s.get(NarasiKasusModel, usulan.sasaran_id)
            periode = _teks_atau_none(kasus.periode) if kasus is not None else None
        if periode is None:
            raise PeriodeTakAdaError("Periode usulan P04 tidak ditemukan.")
        return periode

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

        `TOLAK` menutup baris: `reviewer_approval` dan `disposition` menjadi `DITOLAK`, event
        `DITOLAK` tercatat, dan klaim yang sama langsung boleh diberi klarifikasi baru.

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
        if not setuju:
            rec.disposition = Disposition.DITOLAK.value
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
            KlarifikasiTidakTerbukaError: Sudah `TERJAWAB`/`DIBATALKAN`/`DITOLAK` (409).
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
