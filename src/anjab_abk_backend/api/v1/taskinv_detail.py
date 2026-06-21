"""Endpoint detailing Tahap 3 (per responden)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from ...dependencies import (
    get_current_principal,
    get_ti_detail_service,
    get_ti_responden_service,
    get_ti_sesi_service,
    rate_limit,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse
from ...taskinv.schemas.detail import TiDetailRead, TiDetailSubmit
from ...taskinv.services.detail import TiDetailService
from ...taskinv.services.responden import TiRespondenService
from ...taskinv.services.sesi import TiSesiService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}


@router.post(
    "/responden/{responden_id}/detail",
    response_model=list[TiDetailRead],
    status_code=status.HTTP_201_CREATED,
    summary="Submit detail Tahap 3 untuk satu responden",
    operation_id="taskinv_detail_submit",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_NOT_FOUND_RSP,
        409: {"model": ErrorResponse, "description": "Detail sudah disubmit."},
        422: {"model": ErrorResponse, "description": "task_kode di luar himpunan terpilih."},
    },
)
def submit_detail(
    responden_id: Annotated[str, Path(description="ID responden.")],
    payload: TiDetailSubmit,
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    detail_service: Annotated[TiDetailService, Depends(get_ti_detail_service)],
) -> list[TiDetailRead]:
    responden = rsp_service.get(responden_id)
    sesi = sesi_service.get(responden.sesi_id)
    if sesi.status != "TAHAP3":
        raise ValidationAppError(
            f"Detail Tahap 3 hanya dapat disubmit saat sesi berstatus TAHAP3"
            f" (saat ini: {sesi.status})."
        )
    if responden.tahap3_submit:
        raise ValidationAppError("Responden ini sudah menyelesaikan Tahap 3.")
    valid = set(sesi_service.get_task_terpilih(sesi.id))
    result = detail_service.submit(responden_id, sesi.id, payload, valid)
    rsp_service.mark_tahap3(responden_id)
    return result


@router.get(
    "/responden/{responden_id}/detail",
    response_model=list[TiDetailRead],
    summary="Lihat detail Tahap 3 satu responden",
    operation_id="taskinv_detail_list",
    responses=_NOT_FOUND_RSP,
)
def list_detail(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    detail_service: Annotated[TiDetailService, Depends(get_ti_detail_service)],
) -> list[TiDetailRead]:
    rsp_service.get(responden_id)
    return detail_service.list_by_responden(responden_id)
