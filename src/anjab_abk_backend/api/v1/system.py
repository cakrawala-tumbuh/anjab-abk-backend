"""Endpoint sistem: health, readiness, version, me."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from ... import __version__
from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_ai_run_service,
    get_async_job_service,
    get_current_principal,
    get_readiness_checks,
    get_saklar_ai_service,
    get_skema_db_service,
    idempotency,
    pagination_params,
    require_admin,
)
from ...errors import ServiceUnavailableError
from ...fitur import daftar_fitur
from ...schemas.ai_run import AiRunRead, StatusQaAi
from ...schemas.ai_saklar import SaklarAiAlasan, SaklarAiRead
from ...schemas.async_job import AsyncJobRead
from ...schemas.common import (
    ErrorDetail,
    ErrorResponse,
    FiturKode,
    FiturListRead,
    Health,
    Page,
    VersiRead,
)
from ...schemas.skema_db import SkemaDbRead
from ...security import Principal
from ...services.ai_run import AiRunService
from ...services.ai_saklar import SaklarAiService
from ...services.async_job import AsyncJobService
from ...services.readiness import ReadinessCheck
from ...services.skema_db import SkemaDbService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()


@router.get("/health", response_model=Health, summary="Liveness", tags=["system"])
def health() -> Health:
    return Health(status="ok", version=__version__)


@router.get(
    "/ready",
    response_model=Health,
    summary="Readiness",
    tags=["system"],
    responses={503: {"model": ErrorResponse, "description": "Service belum siap."}},
)
async def ready(
    checks: Annotated[list[ReadinessCheck], Depends(get_readiness_checks)],
) -> Health:
    if checks:
        results = await asyncio.gather(*(c.check() for c in checks), return_exceptions=True)
        failed = [c.name for c, r in zip(checks, results, strict=False) if r is not True]
        if failed:
            raise ServiceUnavailableError(
                "Service belum siap menerima trafik.",
                details=[
                    ErrorDetail(
                        loc=["readiness", name],
                        msg="Check gagal.",
                        type="not_ready",
                        code="not_ready",
                    )
                    for name in failed
                ],
            )
    return Health(status="ready", version=__version__)


@router.get("/version", response_model=VersiRead, summary="Versi", tags=["system"])
def version(settings: Annotated[Settings, Depends(get_settings)]) -> VersiRead:
    """Kembalikan versi aplikasi dan commit build runtime.

    Endpoint publik, tidak menyentuh basis data.

    Returns:
        VersiRead: ``commit`` bernilai ``unknown`` bila ``APP_BUILD_COMMIT`` tak diset.
    """
    return VersiRead(status="ok", version=__version__, commit=settings.app_build_commit)


@router.get(
    "/me",
    response_model=Principal,
    summary="Principal saat ini",
    tags=["system"],
    responses={401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}},
)
def me(principal: Annotated[Principal, Depends(get_current_principal)]) -> Principal:
    return principal


@router.get(
    "/system/fitur",
    response_model=FiturListRead,
    summary="Status feature flag",
    tags=["system"],
    operation_id="system_fitur_list",
    dependencies=READ_GUARDS,
    responses={401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}},
)
def list_fitur(settings: Annotated[Settings, Depends(get_settings)]) -> FiturListRead:
    """Daftar lima feature flag fungsional beserta statusnya (selalu lima entri)."""
    return FiturListRead(items=daftar_fitur(settings))


@router.get(
    "/system/jobs/{job_id}",
    response_model=AsyncJobRead,
    summary="Status job asinkron",
    tags=["system"],
    operation_id="system_job_get",
    dependencies=[Depends(require_admin)],
    responses={
        401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."},
        403: {"model": ErrorResponse, "description": "Bukan admin."},
        404: {"model": ErrorResponse, "description": "Job tidak ditemukan."},
    },
)
def get_job(
    job_id: str, service: Annotated[AsyncJobService, Depends(get_async_job_service)]
) -> AsyncJobRead:
    """Baca status sebuah job asinkron (admin saja)."""
    return service.get(job_id)


@router.get(
    "/system/skema",
    response_model=SkemaDbRead,
    summary="Revisi skema basis data",
    tags=["system"],
    operation_id="system_skema_get",
    dependencies=[Depends(require_admin)],
    responses={
        401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."},
        403: {"model": ErrorResponse, "description": "Bukan admin."},
        503: {"model": ErrorResponse, "description": "Basis data tak terjangkau."},
    },
)
def get_skema(
    service: Annotated[SkemaDbService, Depends(get_skema_db_service)],
) -> SkemaDbRead:
    """Bandingkan skema basis data aktif dengan head migrasi kode dan model ORM (admin saja).

    Hanya membaca; tidak menjalankan migrasi dan tidak memuat data baris. ``selaras`` hanya
    membandingkan revisi, sedangkan ``selisih_model`` membandingkan struktur sebenarnya.
    """
    return service.baca()


_RESP_ADMIN = {
    401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."},
    403: {"model": ErrorResponse, "description": "Bukan admin."},
}


@router.get(
    "/system/ai/runs",
    response_model=Page[AiRunRead],
    summary="Daftar run AI",
    tags=["system"],
    operation_id="system_ai_run_list",
    dependencies=[Depends(require_admin)],
    responses=_RESP_ADMIN,
)
def list_ai_runs(
    service: Annotated[AiRunService, Depends(get_ai_run_service)],
    page: Annotated[Pagination, Depends(pagination_params)],
    fungsi: Annotated[str | None, Query(description="Filter fungsi AI.")] = None,
    status_qa: Annotated[StatusQaAi | None, Query(description="Filter status QA.")] = None,
) -> Page[AiRunRead]:
    """Daftar register run AI, terbaru dulu (admin saja). Tanpa ``masukan``/``keluaran``."""
    items, total = service.list(fungsi, status_qa, page.limit, page.offset)
    return Page[AiRunRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.get(
    "/system/ai/runs/{run_id}",
    response_model=AiRunRead,
    summary="Detail run AI",
    tags=["system"],
    operation_id="system_ai_run_get",
    dependencies=[Depends(require_admin)],
    responses={**_RESP_ADMIN, 404: {"model": ErrorResponse, "description": "Run tak ditemukan."}},
)
def get_ai_run(
    run_id: str, service: Annotated[AiRunService, Depends(get_ai_run_service)]
) -> AiRunRead:
    """Baca satu run AI (admin saja). ``masukan`` dan ``keluaran`` tidak pernah diekspos."""
    return service.get(run_id)


_LAYANAN_SAKLAR = FiturKode.AI_NARRATIVE_DRAFT
_RESP_SAKLAR_AKSI = {
    **_RESP_ADMIN,
    **IDEMPOTENCY_RESPONSES,
    409: {"model": ErrorResponse, "description": "Aksi berulang atau Idempotency-Key diproses."},
}


@router.get(
    "/system/ai/saklar",
    response_model=SaklarAiRead,
    summary="Status kill switch layanan AI",
    tags=["system"],
    operation_id="system_ai_saklar_get",
    dependencies=[Depends(require_admin)],
    responses=_RESP_ADMIN,
)
def get_saklar_ai(
    service: Annotated[SaklarAiService, Depends(get_saklar_ai_service)],
) -> SaklarAiRead:
    """Status saklar: flag env, apakah dimatikan, dan event terakhir (admin saja)."""
    return service.status(_LAYANAN_SAKLAR)


@router.post(
    "/system/ai/saklar/matikan",
    response_model=SaklarAiRead,
    summary="Matikan layanan AI seketika",
    tags=["system"],
    operation_id="system_ai_saklar_matikan",
    dependencies=[Depends(require_admin)],
    responses=_RESP_SAKLAR_AKSI,
)
def matikan_saklar_ai(
    body: SaklarAiAlasan,
    service: Annotated[SaklarAiService, Depends(get_saklar_ai_service)],
    principal: Annotated[Principal, Depends(require_admin)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> SaklarAiRead:
    """Catat event MATIKAN tanpa restart (admin saja). Aktor diambil dari token."""
    return run_idempotent(
        idem,
        response,
        SaklarAiRead,
        lambda: service.matikan(_LAYANAN_SAKLAR, body.alasan, principal.subject),
    )


@router.post(
    "/system/ai/saklar/hidupkan",
    response_model=SaklarAiRead,
    summary="Hidupkan kembali layanan AI",
    tags=["system"],
    operation_id="system_ai_saklar_hidupkan",
    dependencies=[Depends(require_admin)],
    responses=_RESP_SAKLAR_AKSI,
)
def hidupkan_saklar_ai(
    body: SaklarAiAlasan,
    service: Annotated[SaklarAiService, Depends(get_saklar_ai_service)],
    principal: Annotated[Principal, Depends(require_admin)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> SaklarAiRead:
    """Catat event HIDUPKAN (admin saja). Tidak menyalakan flag env: dengan flag mati
    ``boleh_jalan`` tetap ``false``. Aktor diambil dari token."""
    return run_idempotent(
        idem,
        response,
        SaklarAiRead,
        lambda: service.hidupkan(_LAYANAN_SAKLAR, body.alasan, principal.subject),
    )
