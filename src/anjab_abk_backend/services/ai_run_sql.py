"""Implementasi PostgreSQL `AiRunService`."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..errors import ConflictError, NotFoundError, ValidationAppError
from ..models import AiRunModel, _utcnow
from ..schemas.ai_run import AiRunRead, AiSumber, StatusQaAi
from .ai_run import bangun_protocol_id, hash_masukan


class SqlAiRunService:
    """`AiRunService` di atas satu `Session` per request."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._s = session
        self._settings = settings

    def buka(
        self,
        fungsi: str,
        prompt_version: str,
        prompt_hash: str,
        model_diminta: str,
        sumber: list[AiSumber],
        masukan: dict[str, Any],
        dibuat_oleh: str | None = None,
        penyedia: str | None = None,
    ) -> AiRunRead:
        """Simpan run ``MENUNGGU`` dengan ``masukan`` utuh sampai ``tutup``.

        ``penyedia`` dicatat apa adanya, juga untuk run yang akan langsung ditutup gerbang.
        """
        rec = AiRunModel(
            id=str(uuid.uuid4()),
            fungsi=fungsi,
            prompt_version=prompt_version,
            prompt_hash=prompt_hash,
            model_diminta=model_diminta,
            penyedia=penyedia,
            protocol_id=bangun_protocol_id(fungsi, prompt_version, self._settings),
            input_snapshot_id=hash_masukan(masukan),
            sumber=[s.model_dump() for s in sumber],
            masukan=masukan,
            status_qa=StatusQaAi.MENUNGGU.value,
            kode_qa=[],
            dibuat_oleh=dibuat_oleh,
        )
        self._s.add(rec)
        self._s.flush()
        return AiRunRead.model_validate(rec)

    def catat_penyedia(self, run_id: str, penyedia: str) -> bool:
        """Timpa ``penyedia`` run yang masih ``MENUNGGU``; run final tidak pernah diubah.

        Args:
            run_id: Id run.
            penyedia: Mode penyedia yang dipakai tepat sebelum model dipanggil.

        Returns:
            ``True`` bila ditimpa, ``False`` bila run tidak ada atau sudah final.
        """
        rec = self._s.get(AiRunModel, run_id)
        if rec is None or rec.status_qa != StatusQaAi.MENUNGGU.value:
            return False
        rec.penyedia = penyedia
        self._s.flush()
        return True

    def tutup(
        self,
        run_id: str,
        status_qa: StatusQaAi,
        kode_qa: list[str],
        keluaran: dict[str, Any] | None,
        stop_reason: str | None,
        model_dilayani: str | None,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> AiRunRead:
        """Tutup run sekali; ``masukan`` dikosongkan kecuali ``ai_simpan_masukan``."""
        if status_qa is StatusQaAi.MENUNGGU:
            raise ValidationAppError("Status penutup run tidak boleh MENUNGGU.")
        rec = self._s.get(AiRunModel, run_id)
        if rec is None:
            raise NotFoundError(f"Run AI '{run_id}' tidak ditemukan.")
        if rec.status_qa != StatusQaAi.MENUNGGU.value:
            raise ConflictError(f"Run AI '{run_id}' sudah ditutup.")
        rec.status_qa = status_qa.value
        rec.kode_qa = list(kode_qa)
        rec.keluaran = keluaran
        rec.stop_reason = stop_reason
        rec.model_dilayani = model_dilayani
        rec.input_tokens = input_tokens
        rec.output_tokens = output_tokens
        rec.selesai_at = _utcnow()
        if not self._settings.ai_simpan_masukan:
            rec.masukan = None
        self._s.flush()
        return AiRunRead.model_validate(rec)

    def get(self, run_id: str) -> AiRunRead:
        """Baca run atau `NotFoundError`."""
        rec = self._s.get(AiRunModel, run_id)
        if rec is None:
            raise NotFoundError(f"Run AI '{run_id}' tidak ditemukan.")
        return AiRunRead.model_validate(rec)

    def keluaran_internal(self, run_id: str) -> dict[str, Any] | None:
        """Kembalikan salinan `keluaran` run, atau `None` bila belum ada (run `MENUNGGU`/gap).

        Metode internal bagi penyerap narasi; tidak dipasang pada rute mana pun dan
        isinya tidak boleh dicatat ke log.

        Args:
            run_id: Id run.

        Returns:
            Salinan dict keluaran, atau `None` bila kolom kosong.

        Raises:
            NotFoundError: run tak ada.
        """
        rec = self._s.get(AiRunModel, run_id)
        if rec is None:
            raise NotFoundError(f"Run AI '{run_id}' tidak ditemukan.")
        return dict(rec.keluaran) if rec.keluaran is not None else None

    def list(
        self,
        fungsi: str | None,
        status_qa: StatusQaAi | None,
        limit: int,
        offset: int,
    ) -> tuple[list[AiRunRead], int]:
        """Daftar run (terbaru dulu) dengan filter opsional ``fungsi`` dan ``status_qa``."""
        cond = []
        if fungsi is not None:
            cond.append(AiRunModel.fungsi == fungsi)
        if status_qa is not None:
            cond.append(AiRunModel.status_qa == status_qa.value)
        total = self._s.scalar(select(func.count()).select_from(AiRunModel).where(*cond)) or 0
        rows = self._s.scalars(
            select(AiRunModel)
            .where(*cond)
            .order_by(AiRunModel.created_at.desc(), AiRunModel.id)
            .limit(limit)
            .offset(offset)
        ).all()
        return [AiRunRead.model_validate(r) for r in rows], total
