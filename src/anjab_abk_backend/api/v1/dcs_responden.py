"""Endpoint resource `DcsResponden` (penugasan langsung) dan jawaban."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status

from ...config import Settings, get_settings
from ...core.services.partisipan import PartisipanService
from ...dcs.schemas.jawaban import DcsJawabanRead, DcsJawabanUpsert
from ...dcs.schemas.responden import DcsRespondenCreate, DcsRespondenRead
from ...dcs.services.jawaban import DcsJawabanService
from ...dcs.services.responden import DcsRespondenService
from ...dcs.services.subskala import DcsSubSkalaService
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    authorize_responden_access,
    get_current_principal,
    get_dcs_jawaban_service,
    get_dcs_responden_service,
    get_dcs_subskala_service,
    get_kode_orang_service,
    get_partisipan_service,
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
    response_model=Page[DcsRespondenRead],
    summary="Daftar seluruh responden DCS (admin)",
    operation_id="dcs_responden_list",
    dependencies=[Depends(require_admin)],
    responses={**_AUTH, **_FORBIDDEN},
)
def list_responden(
    request: Request,
    response: Response,
    page: Annotated[Pagination, Depends(pagination_params)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
) -> Page[DcsRespondenRead]:
    items, total = rsp_service.list_all(limit=page.limit, offset=page.offset)
    isi_kode_orang(items, ko_service)
    set_pagination_links(response, request, total, page.limit, page.offset)
    return Page[DcsRespondenRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=BulkAssignResult[DcsRespondenRead],
    status_code=status.HTTP_201_CREATED,
    summary="Tugaskan (assign) responden DCS — bulk, idempoten (admin)",
    operation_id="dcs_responden_create",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {
            "model": ErrorResponse,
            "description": "Instrumen DCS tidak OPEN, atau Idempotency-Key sedang diproses.",
        },
    },
)
def create_responden(
    payload: DcsRespondenCreate,
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> BulkAssignResult[DcsRespondenRead]:
    def _assign() -> BulkAssignResult[DcsRespondenRead]:
        hasil = rsp_service.create_banyak(payload.partisipan_ids)
        isi_kode_orang(hasil.created, ko_service, jamin=True)
        return hasil

    return run_idempotent(idem, response, BulkAssignResult[DcsRespondenRead], _assign)


@router.get(
    "/{responden_id}",
    response_model=DcsRespondenRead,
    summary="Ambil detail responden DCS (admin atau pemilik)",
    operation_id="dcs_responden_get",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def get_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    response: Response,
) -> DcsRespondenRead:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    isi_kode_orang([responden], ko_service)
    response.headers["ETag"] = compute_etag(responden)
    return responden


@router.delete(
    "/{responden_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus responden (admin; hanya jika belum submit)",
    operation_id="dcs_responden_delete",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND_RSP, **PRECONDITION_RESPONSES},
)
def delete_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
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
    response_model=list[DcsJawabanRead],
    summary="Simpan draft jawaban (parsial) untuk satu responden",
    operation_id="dcs_jawaban_save_draft",
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
    payload: DcsJawabanUpsert,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
    sk_service: Annotated[DcsSubSkalaService, Depends(get_dcs_subskala_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    if_match: IfMatchHeader = None,
) -> list[DcsJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    check_if_match(jwb_service.list_by_responden(responden_id), if_match, settings.require_if_match)
    if responden.sudah_submit:
        raise ValidationAppError(
            "Responden ini sudah mengirimkan jawaban; draft tidak bisa diubah."
        )
    valid_item_ids = {item.item_id for item in sk_service.list_item()}
    hasil = jwb_service.upsert(responden_id, payload, valid_item_ids)
    response.headers["ETag"] = compute_etag(jwb_service.list_by_responden(responden_id))
    return hasil


@router.post(
    "/{responden_id}/jawaban/submit",
    response_model=list[DcsJawabanRead],
    status_code=status.HTTP_201_CREATED,
    summary="Finalisasi (submit) 42 jawaban tersimpan untuk satu responden",
    operation_id="dcs_jawaban_submit",
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
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
    sk_service: Annotated[DcsSubSkalaService, Depends(get_dcs_subskala_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> list[DcsJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)

    def _submit() -> list[DcsJawabanRead]:
        if responden.sudah_submit:
            raise ValidationAppError("Responden ini sudah mengirimkan jawaban.")
        valid_item_ids = {item.item_id for item in sk_service.list_item()}
        results = jwb_service.submit(responden_id, valid_item_ids)
        rsp_service.mark_submitted(responden_id)
        return results

    return run_idempotent(idem, response, list[DcsJawabanRead], _submit)


@router.get(
    "/{responden_id}/jawaban",
    response_model=list[DcsJawabanRead],
    summary="Lihat jawaban responden DCS (admin atau pemilik)",
    operation_id="dcs_jawaban_list",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def list_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    response: Response,
) -> list[DcsJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    jawaban = jwb_service.list_by_responden(responden_id)
    response.headers["ETag"] = compute_etag(jawaban)
    return jawaban
