"""Endpoint instrumen singleton `DcsInstrumen` (tanpa create/delete — dibuat migrasi)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from ...dcs.schemas.instrumen import DcsInstrumenRead, DcsInstrumenUpdate
from ...dcs.services.instrumen import DcsInstrumenService
from ...dependencies import (
    READ_GUARDS,
    get_current_principal,
    get_dcs_instrumen_service,
    rate_limit,
    require_admin,
)
from ...schemas.common import ErrorResponse
from ...security import Principal

router = APIRouter()

logger = logging.getLogger("anjab_abk_backend.api.v1.dcs_instrumen")

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan admin."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_TRANSISI_INVALID = {422: {"model": ErrorResponse, "description": "Transisi status tidak valid."}}


@router.get(
    "",
    response_model=DcsInstrumenRead,
    summary="Ambil instrumen DCS (singleton)",
    operation_id="dcs_instrumen_get",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE},
)
def get_instrumen(
    service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
) -> DcsInstrumenRead:
    return service.get()


@router.patch(
    "",
    response_model=DcsInstrumenRead,
    summary="Perbarui instrumen DCS (min_responden/catatan)",
    operation_id="dcs_instrumen_update",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE},
)
def update_instrumen(
    payload: DcsInstrumenUpdate,
    service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
) -> DcsInstrumenRead:
    return service.update(payload)


@router.post(
    "/tutup",
    response_model=DcsInstrumenRead,
    summary="Tutup instrumen DCS (OPEN → CLOSED)",
    operation_id="dcs_instrumen_tutup",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_TRANSISI_INVALID},
)
def tutup_instrumen(
    service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
) -> DcsInstrumenRead:
    return service.tutup()


@router.post(
    "/buka-ulang",
    response_model=DcsInstrumenRead,
    summary="Buka ulang instrumen DCS (CLOSED → OPEN)",
    operation_id="dcs_instrumen_buka_ulang",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_TRANSISI_INVALID},
)
def buka_ulang_instrumen(
    service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
) -> DcsInstrumenRead:
    return service.buka_ulang()


@router.post(
    "/reset",
    response_model=DcsInstrumenRead,
    summary="Reset instrumen DCS (admin): hapus SEMUA responden & jawaban, buka kembali (OPEN)",
    operation_id="dcs_instrumen_reset",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def reset_instrumen(
    principal: Annotated[Principal, Depends(require_admin)],
    service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
) -> DcsInstrumenRead:
    """DESTRUKTIF: menghapus seluruh responden DCS (jawaban ikut lewat CASCADE) dan
    mengembalikan instrumen ke OPEN — sah dipanggil dari status APA PUN (idempoten),
    beda dari `/buka-ulang` yang hanya sah dari CLOSED dan tidak menghapus data."""
    logger.warning("instrumen_reset", extra={"modul": "dcs", "actor": principal.subject})
    return service.reset()
