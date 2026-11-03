"""Endpoint instrumen singleton `DcsInstrumen` (tanpa create/delete — dibuat migrasi)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ...config import Settings, get_settings
from ...dcs.schemas.instrumen import DcsInstrumenRead, DcsInstrumenUpdate
from ...dcs.services.instrumen import DcsInstrumenService
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    get_current_principal,
    get_dcs_instrumen_service,
    idempotency,
    rate_limit,
    require_admin,
)
from ...etag import check_if_match, compute_etag
from ...schemas.common import ErrorResponse
from ...security import Principal
from ..concurrency import (
    IDEMPOTENCY_RESPONSES,
    PRECONDITION_RESPONSES,
    IfMatchHeader,
    run_idempotent,
)

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


def _transisi(idem: Idempotency, response: Response, action) -> DcsInstrumenRead:
    """Jalankan transisi instrumen secara idempoten dan pasang header `ETag` hasilnya."""
    hasil = run_idempotent(idem, response, DcsInstrumenRead, action)
    response.headers["ETag"] = compute_etag(hasil)
    return hasil


@router.get(
    "",
    response_model=DcsInstrumenRead,
    summary="Ambil instrumen Dcs (singleton)",
    operation_id="dcs_instrumen_get",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE},
)
def get_instrumen(
    service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
    response: Response,
) -> DcsInstrumenRead:
    instrumen = service.get()
    response.headers["ETag"] = compute_etag(instrumen)
    return instrumen


@router.patch(
    "",
    response_model=DcsInstrumenRead,
    summary="Perbarui instrumen Dcs (min_responden/catatan)",
    operation_id="dcs_instrumen_update",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **PRECONDITION_RESPONSES},
)
def update_instrumen(
    payload: DcsInstrumenUpdate,
    service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: IfMatchHeader = None,
) -> DcsInstrumenRead:
    check_if_match(service.get(), if_match, settings.require_if_match)
    updated = service.update(payload)
    response.headers["ETag"] = compute_etag(updated)
    return updated


@router.post(
    "/tutup",
    response_model=DcsInstrumenRead,
    summary="Tutup instrumen Dcs (OPEN → CLOSED)",
    operation_id="dcs_instrumen_tutup",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_TRANSISI_INVALID, **IDEMPOTENCY_RESPONSES},
)
def tutup_instrumen(
    service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> DcsInstrumenRead:
    return _transisi(idem, response, service.tutup)


@router.post(
    "/buka-ulang",
    response_model=DcsInstrumenRead,
    summary="Buka ulang instrumen Dcs (CLOSED/ANALYZED → OPEN)",
    operation_id="dcs_instrumen_buka_ulang",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_TRANSISI_INVALID, **IDEMPOTENCY_RESPONSES},
)
def buka_ulang_instrumen(
    service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> DcsInstrumenRead:
    return _transisi(idem, response, service.buka_ulang)


@router.post(
    "/reset",
    response_model=DcsInstrumenRead,
    summary="Reset instrumen Dcs (admin): hanya bila belum ada jawaban",
    operation_id="dcs_instrumen_reset",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: _HAS_RESPONSES,
    },
)
def reset_instrumen(
    principal: Annotated[Principal, Depends(require_admin)],
    service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> DcsInstrumenRead:
    """Hapus responden Dcs dan kembalikan instrumen ke OPEN, HANYA bila instrumen belum
    berisi jawaban sama sekali; bila sudah ada jawaban (draft/submit) → 409
    `instrument_has_responses`. Untuk membuka instrumen ANALYZED tanpa menghapus data,
    pakai `/buka-ulang`. Mendukung `Idempotency-Key` (ulangan → 200 hasil tersimpan,
    tanpa reset kedua)."""
    logger.warning("instrumen_reset", extra={"modul": "dcs", "actor": principal.subject})
    return _transisi(idem, response, service.reset)
