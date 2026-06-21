"""Endpoint resource `TsResponden` dalam sesi Time Study."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from ...dependencies import (
    get_current_principal,
    get_ts_responden_service,
    get_ts_sesi_service,
    rate_limit,
)
from ...schemas.common import ErrorResponse
from ...ts.schemas.responden import TsRespondenCreate, TsRespondenRead
from ...ts.services.responden import TsRespondenService
from ...ts.services.sesi import TsSesiService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi Time Study tidak ditemukan."}}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}


@router.get(
    "/{sesi_id}/responden",
    response_model=list[TsRespondenRead],
    summary="Daftar responden dalam sesi Time Study",
    operation_id="ts_responden_list",
    responses=_NOT_FOUND_SESI,
)
def list_responden(
    sesi_id: Annotated[str, Path(description="ID sesi Time Study.")],
    sesi_service: Annotated[TsSesiService, Depends(get_ts_sesi_service)],
    rsp_service: Annotated[TsRespondenService, Depends(get_ts_responden_service)],
) -> list[TsRespondenRead]:
    sesi_service.get(sesi_id)
    return rsp_service.list_by_sesi(sesi_id)


@router.post(
    "/{sesi_id}/responden",
    response_model=TsRespondenRead,
    status_code=status.HTTP_201_CREATED,
    summary="Daftarkan responden ke sesi Time Study",
    operation_id="ts_responden_create",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_NOT_FOUND_SESI,
        409: {
            "model": ErrorResponse,
            "description": "Partisipan sudah terdaftar sebagai responden dalam sesi ini.",
        },
    },
)
def create_responden(
    sesi_id: Annotated[str, Path(description="ID sesi Time Study.")],
    payload: TsRespondenCreate,
    sesi_service: Annotated[TsSesiService, Depends(get_ts_sesi_service)],
    rsp_service: Annotated[TsRespondenService, Depends(get_ts_responden_service)],
) -> TsRespondenRead:
    sesi_service.get(sesi_id)
    return rsp_service.create(sesi_id, payload)


@router.delete(
    "/{sesi_id}/responden/{responden_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus responden dari sesi Time Study",
    operation_id="ts_responden_delete",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND_RSP},
)
def delete_responden(
    sesi_id: Annotated[str, Path(description="ID sesi Time Study.")],
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[TsRespondenService, Depends(get_ts_responden_service)],
) -> Response:
    rsp_service.delete(responden_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
