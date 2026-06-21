"""Endpoint resource `TiResponden`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from ...dependencies import (
    get_current_principal,
    get_ti_responden_service,
    get_ti_sesi_service,
    rate_limit,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse
from ...taskinv.schemas.responden import TiRespondenCreate, TiRespondenRead
from ...taskinv.services.responden import TiRespondenService
from ...taskinv.services.sesi import TiSesiService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi tidak ditemukan."}}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}


@router.get(
    "/{sesi_id}/responden",
    response_model=list[TiRespondenRead],
    summary="Daftar responden dalam sesi",
    operation_id="taskinv_responden_list",
    responses=_NOT_FOUND_SESI,
)
def list_responden(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
) -> list[TiRespondenRead]:
    sesi_service.get(sesi_id)
    return rsp_service.list_by_sesi(sesi_id)


@router.post(
    "/{sesi_id}/responden",
    response_model=TiRespondenRead,
    status_code=status.HTTP_201_CREATED,
    summary="Daftarkan responden ke sesi (saat DRAFT/TAHAP1)",
    operation_id="taskinv_responden_create",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND_SESI},
)
def create_responden(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    payload: TiRespondenCreate,
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
) -> TiRespondenRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status not in ("DRAFT", "TAHAP1"):
        raise ValidationAppError(
            "Responden hanya dapat ditambahkan saat sesi berstatus DRAFT atau TAHAP1"
            f" (saat ini: {sesi.status})."
        )
    return rsp_service.create(sesi_id, payload, sesi.max_responden)


@router.get(
    "/responden/{responden_id}",
    response_model=TiRespondenRead,
    summary="Ambil detail responden",
    operation_id="taskinv_responden_get",
    responses=_NOT_FOUND_RSP,
)
def get_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
) -> TiRespondenRead:
    return rsp_service.get(responden_id)


@router.delete(
    "/responden/{responden_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus responden (hanya jika belum submit)",
    operation_id="taskinv_responden_delete",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND_RSP},
)
def delete_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
) -> Response:
    rsp_service.delete(responden_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
