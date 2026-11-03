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


_HAS_RESPONSES = {
    "model": ErrorResponse,
    "description": "Instrumen sudah berisi jawaban (`instrument_has_responses`).",
}


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
    summary="Buka ulang instrumen DCS (CLOSED/ANALYZED → OPEN)",
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
    summary="Reset instrumen DCS (admin): hanya bila belum ada jawaban",
    operation_id="dcs_instrumen_reset",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, 409: _HAS_RESPONSES},
)
def reset_instrumen(
    principal: Annotated[Principal, Depends(require_admin)],
    service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
) -> DcsInstrumenRead:
    """Hapus responden DCS dan kembalikan instrumen ke OPEN, HANYA bila instrumen belum
    berisi jawaban sama sekali; bila sudah ada jawaban (draft/submit) → 409
    `instrument_has_responses`. Untuk membuka instrumen ANALYZED tanpa menghapus data,
    pakai `/buka-ulang`."""
    logger.warning("instrumen_reset", extra={"modul": "dcs", "actor": principal.subject})
    return service.reset()
