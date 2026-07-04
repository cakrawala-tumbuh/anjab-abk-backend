"""Endpoint resource `TiResponden`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from ...anjab.services.sme_panel import SMEPanelService
from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    authorize_responden_access,
    get_current_principal,
    get_partisipan_service,
    get_sme_panel_service,
    get_ti_responden_service,
    get_ti_sesi_service,
    rate_limit,
    require_admin,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...taskinv.schemas.responden import TiRespondenCreate, TiRespondenRead
from ...taskinv.services.responden import TiRespondenService
from ...taskinv.services.sesi import TiSesiService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi tidak ditemukan."}}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik responden."}
}


@router.get(
    "/{sesi_id}/responden",
    response_model=list[TiRespondenRead],
    summary="Daftar responden dalam sesi (admin)",
    operation_id="taskinv_responden_list",
    dependencies=[Depends(require_admin)],
    responses={**_AUTH, **_FORBIDDEN, **_NOT_FOUND_SESI},
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
    summary="Daftarkan responden ke sesi (admin; saat DRAFT/TAHAP1)",
    operation_id="taskinv_responden_create",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_SESI,
        422: {
            "model": ErrorResponse,
            "description": "Partisipan bukan anggota SME panel jabatan sesi ini.",
        },
    },
)
def create_responden(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    payload: TiRespondenCreate,
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    sme_panel_service: Annotated[SMEPanelService, Depends(get_sme_panel_service)],
) -> TiRespondenRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status not in ("DRAFT", "TAHAP1"):
        raise ValidationAppError(
            "Responden hanya dapat ditambahkan saat sesi berstatus DRAFT atau TAHAP1"
            f" (saat ini: {sesi.status})."
        )
    if sesi.jabatan_id and payload.partisipan_id:
        panels, _ = sme_panel_service.search(
            domain=[["jabatan_id", "=", sesi.jabatan_id]],
            order=[],
            limit=1,
            offset=0,
        )
        if not panels:
            raise ValidationAppError("SME panel untuk jabatan sesi ini belum dibuat.")
        if payload.partisipan_id not in panels[0].partisipan_ids:
            raise ValidationAppError(
                "Partisipan tidak dapat ditambahkan:"
                " belum tergabung dalam SME panel jabatan ini."
            )
    return rsp_service.create(sesi_id, payload, sesi.max_responden)


@router.get(
    "/responden/{responden_id}",
    response_model=TiRespondenRead,
    summary="Ambil detail responden (admin atau pemilik)",
    operation_id="taskinv_responden_get",
    responses={**_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def get_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> TiRespondenRead:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    return responden


@router.delete(
    "/responden/{responden_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus responden (admin; hanya jika belum submit)",
    operation_id="taskinv_responden_delete",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def delete_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
) -> Response:
    rsp_service.delete(responden_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
