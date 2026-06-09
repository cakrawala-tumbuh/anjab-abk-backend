"""Endpoint sistem: health, readiness, version, me."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends

from ... import __version__
from ...dependencies import get_current_principal, get_readiness_checks
from ...errors import ServiceUnavailableError
from ...schemas.common import ErrorDetail, ErrorResponse, Health
from ...security import Principal
from ...services.readiness import ReadinessCheck

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


@router.get("/version", response_model=Health, summary="Versi", tags=["system"])
def version() -> Health:
    return Health(status="ok", version=__version__)


@router.get(
    "/me",
    response_model=Principal,
    summary="Principal saat ini",
    tags=["system"],
    responses={401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}},
)
def me(principal: Annotated[Principal, Depends(get_current_principal)]) -> Principal:
    return principal
