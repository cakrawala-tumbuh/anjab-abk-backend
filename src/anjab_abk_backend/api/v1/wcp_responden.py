"""Endpoint resource `WcpResponden` (penugasan langsung) dan jawaban."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    READ_GUARDS,
    Pagination,
    authorize_responden_access,
    get_current_principal,
    get_partisipan_service,
    get_wcp_dimensi_service,
    get_wcp_jawaban_service,
    get_wcp_responden_service,
    pagination_params,
    rate_limit,
    require_admin,
)
from ...errors import ValidationAppError
from ...schemas.common import BulkAssignResult, ErrorResponse, Page
from ...security import Principal
from ...wcp.schemas.jawaban import WcpJawabanRead, WcpJawabanUpsert
from ...wcp.schemas.responden import WcpRespondenCreate, WcpRespondenRead
from ...wcp.services.dimensi import WcpDimensiService
from ...wcp.services.jawaban import WcpJawabanService
from ...wcp.services.responden import WcpRespondenService
from ..pagination import set_pagination_links

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik responden."}
}


@router.get(
    "",
    response_model=Page[WcpRespondenRead],
    summary="Daftar seluruh responden WCP (admin)",
    operation_id="wcp_responden_list",
    dependencies=[Depends(require_admin)],
    responses={**_AUTH, **_FORBIDDEN},
)
def list_responden(
    request: Request,
    response: Response,
    page: Annotated[Pagination, Depends(pagination_params)],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
) -> Page[WcpRespondenRead]:
    items, total = rsp_service.list_all(limit=page.limit, offset=page.offset)
    set_pagination_links(response, request, total, page.limit, page.offset)
    return Page[WcpRespondenRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=BulkAssignResult[WcpRespondenRead],
    status_code=status.HTTP_201_CREATED,
    summary="Tugaskan (assign) responden WCP — bulk, idempoten (admin)",
    operation_id="wcp_responden_create",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {
            "model": ErrorResponse,
            "description": "Instrumen WCP tidak OPEN.",
        },
    },
)
def create_responden(
    payload: WcpRespondenCreate,
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
) -> BulkAssignResult[WcpRespondenRead]:
    return rsp_service.create_banyak(payload.partisipan_ids)


@router.get(
    "/{responden_id}",
    response_model=WcpRespondenRead,
    summary="Ambil detail responden WCP (admin atau pemilik)",
    operation_id="wcp_responden_get",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
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
    "/{responden_id}",
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


@router.put(
    "/{responden_id}/jawaban",
    response_model=list[WcpJawabanRead],
    summary="Simpan draft jawaban (parsial) untuk satu responden",
    operation_id="wcp_jawaban_save_draft",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_RSP,
        409: {"model": ErrorResponse, "description": "Item tidak dikenal."},
        422: {
            "model": ErrorResponse,
            "description": "Responden sudah submit final, atau instrumen tidak OPEN.",
        },
    },
)
def save_draft_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    payload: WcpJawabanUpsert,
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    jwb_service: Annotated[WcpJawabanService, Depends(get_wcp_jawaban_service)],
    dim_service: Annotated[WcpDimensiService, Depends(get_wcp_dimensi_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> list[WcpJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    if responden.sudah_submit:
        raise ValidationAppError(
            "Responden ini sudah mengirimkan jawaban; draft tidak bisa diubah."
        )
    valid_item_ids = {item.item_id for item in dim_service.list_item()}
    return jwb_service.upsert(responden_id, payload, valid_item_ids)


@router.post(
    "/{responden_id}/jawaban/submit",
    response_model=list[WcpJawabanRead],
    status_code=status.HTTP_201_CREATED,
    summary="Finalisasi (submit) 72 jawaban tersimpan untuk satu responden",
    operation_id="wcp_jawaban_submit",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_RSP,
        422: {
            "model": ErrorResponse,
            "description": (
                "Responden sudah submit, jawaban tersimpan belum lengkap, atau instrumen"
                " tidak OPEN."
            ),
        },
    },
)
def submit_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
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
    results = jwb_service.submit(responden_id, valid_item_ids)
    rsp_service.mark_submitted(responden_id)
    return results


@router.get(
    "/{responden_id}/jawaban",
    response_model=list[WcpJawabanRead],
    summary="Lihat jawaban responden (admin atau pemilik)",
    operation_id="wcp_jawaban_list",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
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
