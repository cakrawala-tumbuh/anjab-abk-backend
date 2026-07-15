"""Endpoint instrumen singleton `WcpInstrumen` (tanpa create/delete — dibuat migrasi)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from ...dependencies import (
    READ_GUARDS,
    get_current_principal,
    get_wcp_instrumen_service,
    rate_limit,
    require_admin,
)
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...wcp.schemas.instrumen import WcpInstrumenRead, WcpInstrumenUpdate
from ...wcp.services.instrumen import WcpInstrumenService

router = APIRouter()

logger = logging.getLogger("anjab_abk_backend.api.v1.wcp_instrumen")

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan admin."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_TRANSISI_INVALID = {422: {"model": ErrorResponse, "description": "Transisi status tidak valid."}}


@router.get(
    "",
    response_model=WcpInstrumenRead,
    summary="Ambil instrumen WCP (singleton)",
    operation_id="wcp_instrumen_get",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE},
)
def get_instrumen(
    service: Annotated[WcpInstrumenService, Depends(get_wcp_instrumen_service)],
) -> WcpInstrumenRead:
    return service.get()


@router.patch(
    "",
    response_model=WcpInstrumenRead,
    summary="Perbarui instrumen WCP (min_responden/catatan)",
    operation_id="wcp_instrumen_update",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE},
)
def update_instrumen(
    payload: WcpInstrumenUpdate,
    service: Annotated[WcpInstrumenService, Depends(get_wcp_instrumen_service)],
) -> WcpInstrumenRead:
    return service.update(payload)


@router.post(
    "/tutup",
    response_model=WcpInstrumenRead,
    summary="Tutup instrumen WCP (OPEN → CLOSED)",
    operation_id="wcp_instrumen_tutup",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_TRANSISI_INVALID},
)
def tutup_instrumen(
    service: Annotated[WcpInstrumenService, Depends(get_wcp_instrumen_service)],
) -> WcpInstrumenRead:
    return service.tutup()


@router.post(
    "/buka-ulang",
    response_model=WcpInstrumenRead,
    summary="Buka ulang instrumen WCP (CLOSED → OPEN)",
    operation_id="wcp_instrumen_buka_ulang",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_TRANSISI_INVALID},
)
def buka_ulang_instrumen(
    service: Annotated[WcpInstrumenService, Depends(get_wcp_instrumen_service)],
) -> WcpInstrumenRead:
    return service.buka_ulang()


@router.post(
    "/reset",
    response_model=WcpInstrumenRead,
    summary="Reset instrumen WCP (admin): hapus SEMUA responden & jawaban, buka kembali (OPEN)",
    operation_id="wcp_instrumen_reset",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def reset_instrumen(
    principal: Annotated[Principal, Depends(require_admin)],
    service: Annotated[WcpInstrumenService, Depends(get_wcp_instrumen_service)],
) -> WcpInstrumenRead:
    """DESTRUKTIF: menghapus seluruh responden WCP (jawaban ikut lewat CASCADE) dan
    mengembalikan instrumen ke OPEN — sah dipanggil dari status APA PUN (idempoten),
    beda dari `/buka-ulang` yang hanya sah dari CLOSED dan tidak menghapus data."""
    logger.warning("instrumen_reset", extra={"modul": "wcp", "actor": principal.subject})
    return service.reset()
