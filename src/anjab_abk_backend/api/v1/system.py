"""Endpoint sistem: health, readiness, version, me."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from ... import __version__
from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    get_async_job_service,
    get_current_principal,
    get_readiness_checks,
    get_skema_db_service,
    require_admin,
)
from ...errors import ServiceUnavailableError
from ...fitur import daftar_fitur
from ...schemas.async_job import AsyncJobRead
from ...schemas.common import ErrorDetail, ErrorResponse, FiturListRead, Health, VersiRead
from ...schemas.skema_db import SkemaDbRead
from ...security import Principal
from ...services.async_job import AsyncJobService
from ...services.readiness import ReadinessCheck
from ...services.skema_db import SkemaDbService

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
