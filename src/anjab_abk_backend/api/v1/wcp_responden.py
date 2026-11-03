"""Endpoint resource `WcpResponden` (penugasan langsung) dan jawaban."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status

from ...config import Settings, get_settings
from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    authorize_responden_access,
    get_current_principal,
    get_kode_orang_service,
    get_partisipan_service,
    get_wcp_dimensi_service,
    get_wcp_jawaban_service,
    get_wcp_responden_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_admin,
)
from ...errors import ValidationAppError
from ...etag import check_if_match, compute_etag
from ...redesain.services.kode_orang import KodeOrangService
from ...schemas.common import BulkAssignResult, ErrorResponse, Page
from ...security import Principal
from ...wcp.schemas.jawaban import WcpJawabanRead, WcpJawabanUpsert
from ...wcp.schemas.responden import WcpRespondenCreate, WcpRespondenRead
from ...wcp.services.dimensi import WcpDimensiService
from ...wcp.services.jawaban import WcpJawabanService
from ...wcp.services.responden import WcpRespondenService
from ..concurrency import (
    IDEMPOTENCY_RESPONSES,
    PRECONDITION_RESPONSES,
    IfMatchHeader,
    run_idempotent,
)
from ..kode_orang_isi import isi_kode_orang
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
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
) -> Page[WcpRespondenRead]:
    items, total = rsp_service.list_all(limit=page.limit, offset=page.offset)
    isi_kode_orang(items, ko_service)
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
            "description": "Instrumen WCP tidak OPEN, atau Idempotency-Key sedang diproses.",
        },
    },
)
def create_responden(
    payload: WcpRespondenCreate,
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> BulkAssignResult[WcpRespondenRead]:
    def _assign() -> BulkAssignResult[WcpRespondenRead]:
        hasil = rsp_service.create_banyak(payload.partisipan_ids)
        isi_kode_orang(hasil.created, ko_service, jamin=True)
        return hasil

    return run_idempotent(idem, response, BulkAssignResult[WcpRespondenRead], _assign)


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
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    response: Response,
) -> WcpRespondenRead:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    isi_kode_orang([responden], ko_service)
    response.headers["ETag"] = compute_etag(responden)
    return responden


@router.delete(
    "/{responden_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus responden (admin; hanya jika belum submit)",
    operation_id="wcp_responden_delete",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND_RSP, **PRECONDITION_RESPONSES},
)
def delete_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    if_match: IfMatchHeader = None,
) -> Response:
    responden = rsp_service.get(responden_id)
    isi_kode_orang([responden], ko_service)
    check_if_match(responden, if_match, settings.require_if_match)
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
        **PRECONDITION_RESPONSES,
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
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    jwb_service: Annotated[WcpJawabanService, Depends(get_wcp_jawaban_service)],
    dim_service: Annotated[WcpDimensiService, Depends(get_wcp_dimensi_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    if_match: IfMatchHeader = None,
) -> list[WcpJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    check_if_match(jwb_service.list_by_responden(responden_id), if_match, settings.require_if_match)
    if responden.sudah_submit:
        raise ValidationAppError(
            "Responden ini sudah mengirimkan jawaban; draft tidak bisa diubah."
        )
    valid_item_ids = {item.item_id for item in dim_service.list_item()}
    hasil = jwb_service.upsert(responden_id, payload, valid_item_ids)
    response.headers["ETag"] = compute_etag(jwb_service.list_by_responden(responden_id))
    return hasil


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
        **IDEMPOTENCY_RESPONSES,
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
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> list[WcpJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)

    def _submit() -> list[WcpJawabanRead]:
        if responden.sudah_submit:
            raise ValidationAppError("Responden ini sudah mengirimkan jawaban.")
        valid_item_ids = {item.item_id for item in dim_service.list_item()}
        results = jwb_service.submit(responden_id, valid_item_ids)
        rsp_service.mark_submitted(responden_id)
        return results

    return run_idempotent(idem, response, list[WcpJawabanRead], _submit)


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
    response: Response,
) -> list[WcpJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    jawaban = jwb_service.list_by_responden(responden_id)
    response.headers["ETag"] = compute_etag(jawaban)
    return jawaban
