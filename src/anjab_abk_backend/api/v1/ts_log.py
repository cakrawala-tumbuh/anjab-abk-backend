"""Endpoint resource `TsLog` (log harian Time Study)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from ...dependencies import (
    get_current_principal,
    get_ts_log_service,
    get_ts_responden_service,
    rate_limit,
)
from ...schemas.common import ErrorResponse
from ...ts.schemas.log import TsLogCreate, TsLogRead, TsLogUpdate
from ...ts.services.log import TsLogService
from ...ts.services.responden import TsRespondenService

router = APIRouter()

_AUTH_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_NOT_FOUND_LOG = {404: {"model": ErrorResponse, "description": "Log tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}


@router.get(
    "/{responden_id}/log",
    response_model=list[TsLogRead],
    summary="Daftar log harian responden Time Study",
    operation_id="ts_log_list",
    dependencies=_AUTH_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND_RSP},
)
def list_log(
    responden_id: Annotated[str, Path(description="ID responden Time Study.")],
    rsp_service: Annotated[TsRespondenService, Depends(get_ts_responden_service)],
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
) -> list[TsLogRead]:
    rsp_service.get(responden_id)
    return log_service.list_by_responden(responden_id)


@router.post(
    "/{responden_id}/log",
    response_model=TsLogRead,
    status_code=status.HTTP_201_CREATED,
    summary="Tambah log harian untuk responden Time Study",
    operation_id="ts_log_create",
    dependencies=_AUTH_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_NOT_FOUND_RSP,
        409: {"model": ErrorResponse, "description": "Log untuk tanggal ini sudah ada."},
    },
)
def create_log(
    responden_id: Annotated[str, Path(description="ID responden Time Study.")],
    payload: TsLogCreate,
    rsp_service: Annotated[TsRespondenService, Depends(get_ts_responden_service)],
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
) -> TsLogRead:
    rsp_service.get(responden_id)
    return log_service.create(responden_id, payload)


@router.get(
    "/{responden_id}/log/{log_id}",
    response_model=TsLogRead,
    summary="Ambil detail log harian Time Study",
    operation_id="ts_log_get",
    dependencies=_AUTH_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND_LOG},
)
def get_log(
    responden_id: Annotated[str, Path(description="ID responden Time Study.")],
    log_id: Annotated[str, Path(description="ID log.")],
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
) -> TsLogRead:
    return log_service.get(log_id)


@router.patch(
    "/{responden_id}/log/{log_id}",
    response_model=TsLogRead,
    summary="Perbarui log harian Time Study",
    operation_id="ts_log_update",
    dependencies=_AUTH_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND_LOG},
)
def update_log(
    responden_id: Annotated[str, Path(description="ID responden Time Study.")],
    log_id: Annotated[str, Path(description="ID log.")],
    payload: TsLogUpdate,
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
) -> TsLogRead:
    return log_service.update(log_id, payload)
