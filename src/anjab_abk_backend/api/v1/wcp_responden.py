"""Endpoint resource `WcpResponden` dan submit jawaban."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    authorize_responden_access,
    get_current_principal,
    get_partisipan_service,
    get_wcp_dimensi_service,
    get_wcp_jawaban_service,
    get_wcp_responden_service,
    get_wcp_sesi_service,
    rate_limit,
    require_admin,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...wcp.schemas.jawaban import WcpJawabanBulkCreate, WcpJawabanRead
from ...wcp.schemas.responden import WcpRespondenCreate, WcpRespondenRead
from ...wcp.services.dimensi import WcpDimensiService
from ...wcp.services.jawaban import WcpJawabanService
from ...wcp.services.responden import WcpRespondenService
from ...wcp.services.sesi import WcpSesiService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi WCP tidak ditemukan."}}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik responden."}
}


@router.get(
    "/{sesi_id}/responden",
    response_model=list[WcpRespondenRead],
    summary="Daftar responden dalam sesi WCP (admin)",
    operation_id="wcp_responden_list",
    dependencies=[Depends(require_admin)],
    responses={**_AUTH, **_FORBIDDEN, **_NOT_FOUND_SESI},
)
def list_responden(
    sesi_id: Annotated[str, Path(description="ID sesi WCP.")],
    sesi_service: Annotated[WcpSesiService, Depends(get_wcp_sesi_service)],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
) -> list[WcpRespondenRead]:
    sesi_service.get(sesi_id)
    return rsp_service.list_by_sesi(sesi_id)


@router.post(
    "/{sesi_id}/responden",
    response_model=WcpRespondenRead,
    status_code=status.HTTP_201_CREATED,
    summary="Daftarkan responden ke sesi WCP (admin)",
    operation_id="wcp_responden_create",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_SESI,
        409: {
            "model": ErrorResponse,
            "description": "Partisipan sudah terdaftar sebagai responden WCP.",
        },
    },
)
def create_responden(
    sesi_id: Annotated[str, Path(description="ID sesi WCP.")],
    payload: WcpRespondenCreate,
    sesi_service: Annotated[WcpSesiService, Depends(get_wcp_sesi_service)],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
) -> WcpRespondenRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status != "OPEN":
        raise ValidationAppError(
            f"Responden hanya dapat ditambahkan saat sesi berstatus OPEN (saat ini: {sesi.status})."
        )
    return rsp_service.create(sesi_id, payload, sesi.max_responden)


@router.get(
    "/responden/{responden_id}",
    response_model=WcpRespondenRead,
    summary="Ambil detail responden WCP (admin atau pemilik)",
    operation_id="wcp_responden_get",
    responses={**_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def get_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> WcpRespondenRead:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    return responden


@router.delete(
    "/responden/{responden_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus responden (admin; hanya jika belum submit)",
    operation_id="wcp_responden_delete",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def delete_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
) -> Response:
    rsp_service.delete(responden_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/responden/{responden_id}/jawaban",
    response_model=list[WcpJawabanRead],
    status_code=status.HTTP_201_CREATED,
    summary="Submit 72 jawaban untuk satu responden",
    operation_id="wcp_jawaban_submit",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_RSP,
        409: {"model": ErrorResponse, "description": "Jawaban sudah ada atau item tidak valid."},
    },
)
def submit_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    payload: WcpJawabanBulkCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    jwb_service: Annotated[WcpJawabanService, Depends(get_wcp_jawaban_service)],
    dim_service: Annotated[WcpDimensiService, Depends(get_wcp_dimensi_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> list[WcpJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    if responden.sudah_submit:
        raise ValidationAppError("Responden ini sudah mengirimkan jawaban.")
    valid_item_ids = {item.item_id for item in dim_service.list_item()}
    results = jwb_service.bulk_create(responden_id, payload, valid_item_ids)
    rsp_service.mark_submitted(responden_id)
    return results


@router.get(
    "/responden/{responden_id}/jawaban",
    response_model=list[WcpJawabanRead],
    summary="Lihat jawaban responden (admin atau pemilik)",
    operation_id="wcp_jawaban_list",
    responses={**_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def list_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    jwb_service: Annotated[WcpJawabanService, Depends(get_wcp_jawaban_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> list[WcpJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    return jwb_service.list_by_responden(responden_id)
