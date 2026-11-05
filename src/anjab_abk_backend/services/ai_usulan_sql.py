"""Implementasi `AiUsulanService` di atas PostgreSQL (SQLAlchemy 2.0, sinkron)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai.gateway import AiGateway
from ..ai.redaksi import SumberAi
from ..config import Settings
from ..errors import NotFoundError
from ..fitur import FiturNonaktifError, ai_boleh_jalan
from ..models import AiUsulanModel
from ..schemas.ai_usulan import AiUsulanRingkas, SasaranUsulan
from ..schemas.common import FiturKode
from ..security import Principal
from .ai_usulan import (
    FungsiAiBelumAktifError,
    PiiModeAiBelumDidukungError,
    UsulanBerjalanError,
)

__all__ = ["SqlAiUsulanService"]


class SqlAiUsulanService:
    """`AiUsulanService` berbasis PostgreSQL; terikat satu `Session`.

    Hanya menulis `ai_usulan` (dan, lewat gateway, `ai_run`/`async_job`); tidak pernah
    menyentuh tabel `narasi_*`. Pemilik sesi yang melakukan commit.
    """

    def __init__(self, session: Session, settings: Settings, gateway: AiGateway) -> None:
        """Siapkan layanan.

        Args:
            session: Sesi basis data.
            settings: Pengaturan aplikasi.
            gateway: Gateway pengajuan job AI di atas sesi yang sama.
        """
        self._s = session
        self._settings = settings
        self._gateway = gateway

    def ajukan(
        self,
        fungsi: str,
        sasaran_jenis: SasaranUsulan,
        sasaran_id: str,
        sumber: list[SumberAi],
        parameter: dict[str, Any],
        principal: Principal,
    ) -> AiUsulanRingkas:
        """Ajukan fungsi AI atas satu sasaran lalu catat usulannya.

        Urutan periksa mengikat, tidak ada baris ditulis sebelum semuanya lolos: flag/saklar
        AI, mode PII, usulan berjalan, lalu pengajuan lewat gateway.

        Args:
            fungsi: Kode fungsi terdaftar.
            sasaran_jenis: Jenis objek sasaran.
            sasaran_id: Id objek sasaran.
            sumber: Sumber data calon masukan model.
            parameter: Parameter fungsi (tanpa PII).
            principal: Pemohon; `subject` dicatat sebagai `diminta_oleh`.

        Returns:
            Proyeksi usulan yang baru dicatat (belum diserap).

        Raises:
            FiturNonaktifError: flag atau saklar AI mati (409 `feature_disabled`).
            PiiModeAiBelumDidukungError: `AI_PII_MODE` bukan `BLOKIR` (409).
            UsulanBerjalanError: usulan `fungsi` + `sasaran_id` sama belum diserap (409).
            FungsiAiBelumAktifError: fungsi belum terdaftar (409).
        """
        if not ai_boleh_jalan(self._s, self._settings, FiturKode.AI_NARRATIVE_DRAFT):
            raise FiturNonaktifError(FiturKode.AI_NARRATIVE_DRAFT)
        if self._settings.ai_pii_mode != "BLOKIR":
            raise PiiModeAiBelumDidukungError("Hanya AI_PII_MODE=BLOKIR yang didukung.")
        berjalan = self._s.scalar(
            select(AiUsulanModel.id)
            .where(
                AiUsulanModel.fungsi == fungsi,
                AiUsulanModel.sasaran_id == sasaran_id,
                AiUsulanModel.diserap_at.is_(None),
            )
            .limit(1)
        )
        if berjalan is not None:
            raise UsulanBerjalanError("Sasaran ini masih punya usulan AI yang belum diserap.")
        try:
            job = self._gateway.ajukan(fungsi, sumber, parameter, None, principal.subject)
        except NotFoundError as exc:
            raise FungsiAiBelumAktifError(f"Fungsi AI {fungsi} belum diaktifkan.") from exc
        if not job.ref_id:
            raise RuntimeError("Job AI tanpa ref_id run.")
        rec = AiUsulanModel(
            id=str(uuid.uuid4()),
            fungsi=fungsi,
            sasaran_jenis=sasaran_jenis.value,
            sasaran_id=sasaran_id,
            job_id=job.id,
            ai_run_id=job.ref_id,
            sumber_ids=[s.source_id for s in sumber],
            diminta_oleh=principal.subject,
        )
        self._s.add(rec)
        self._s.flush()
        self._s.refresh(rec)
        return AiUsulanRingkas.model_validate(rec)
