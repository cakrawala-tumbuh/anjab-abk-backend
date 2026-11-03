"""Endpoint detailing Tahap 3 (per responden)."""

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
    get_partisipan_service,
    get_ti_detail_service,
    get_ti_responden_service,
    get_ti_sesi_service,
    idempotency,
    pagination_params,
    rate_limit,
)
from ...errors import ValidationAppError
from ...etag import check_if_match, compute_etag
from ...schemas.common import ErrorResponse, Page
from ...security import Principal
from ...taskinv.schemas.detail import TiDetailRead, TiDetailUpsert
from ...taskinv.services.detail import TiDetailService
from ...taskinv.services.responden import TiRespondenService
from ...taskinv.services.sesi import TiSesiService
from ..concurrency import (
    IDEMPOTENCY_RESPONSES,
    PRECONDITION_RESPONSES,
    IfMatchHeader,
    run_idempotent,
)
from ..pagination import set_pagination_links

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik responden."}
}


@router.put(
    "/responden/{responden_id}/detail",
    response_model=list[TiDetailRead],
    summary="Simpan draft detail (parsial) Tahap 3 untuk satu responden",
    operation_id="taskinv_detail_save_draft",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_RSP,
        **PRECONDITION_RESPONSES,
        422: {
            "model": ErrorResponse,
            "description": "task_kode di luar himpunan terpilih, sesi bukan TAHAP3,"
            " atau responden sudah submit.",
        },
    },
)
def save_draft_detail(
    responden_id: Annotated[str, Path(description="ID responden.")],
    payload: TiDetailUpsert,
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    detail_service: Annotated[TiDetailService, Depends(get_ti_detail_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: IfMatchHeader = None,
) -> list[TiDetailRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    check_if_match(
        detail_service.list_by_responden(responden_id)[0], if_match, settings.require_if_match
    )
    sesi = sesi_service.get(responden.sesi_id)
    if sesi.status != "TAHAP3":
        raise ValidationAppError(
            f"Detail Tahap 3 hanya dapat disimpan saat sesi berstatus TAHAP3"
            f" (saat ini: {sesi.status})."
        )
    if responden.tahap3_submit:
        raise ValidationAppError(
            "Responden ini sudah menyelesaikan Tahap 3; draft tidak bisa diubah."
        )
    kodes, _ = sesi_service.get_task_terpilih(sesi.id)
    valid = set(kodes)
    hasil = detail_service.upsert(responden_id, sesi.id, payload, valid)
    response.headers["ETag"] = compute_etag(detail_service.list_by_responden(responden_id)[0])
    return hasil


@router.post(
    "/responden/{responden_id}/detail/submit",
    response_model=list[TiDetailRead],
    status_code=status.HTTP_201_CREATED,
    summary="Finalisasi (submit) detail Tahap 3 tersimpan untuk satu responden",
    operation_id="taskinv_detail_submit",
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
                "Sesi bukan TAHAP3, responden sudah submit, belum ada entri detail, ada"
                " entri belum lengkap kelima field CalHR-nya, atau masih ada entri"
                ' ber-va_type "Context-Dependent" yang belum difinalisasi.'
            ),
        },
    },
)
def submit_detail(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    detail_service: Annotated[TiDetailService, Depends(get_ti_detail_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> list[TiDetailRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)

    def _submit() -> list[TiDetailRead]:
        sesi = sesi_service.get(responden.sesi_id)
        if sesi.status != "TAHAP3":
            raise ValidationAppError(
                f"Detail Tahap 3 hanya dapat disubmit saat sesi berstatus TAHAP3"
                f" (saat ini: {sesi.status})."
            )
        if responden.tahap3_submit:
            raise ValidationAppError("Responden ini sudah menyelesaikan Tahap 3.")
        result = detail_service.submit(responden_id)
        rsp_service.mark_tahap3(responden_id)
        return result

    return run_idempotent(idem, response, list[TiDetailRead], _submit)


@router.get(
    "/responden/{responden_id}/detail",
    response_model=Page[TiDetailRead],
    summary="Lihat detail Tahap 3 satu responden (admin atau pemilik)",
    operation_id="taskinv_detail_list",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def list_detail(
    responden_id: Annotated[str, Path(description="ID responden.")],
    request: Request,
    response: Response,
    page: Annotated[Pagination, Depends(pagination_params)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    detail_service: Annotated[TiDetailService, Depends(get_ti_detail_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> Page[TiDetailRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    items, total = detail_service.list_by_responden(
        responden_id, limit=page.limit, offset=page.offset
    )
    response.headers["ETag"] = compute_etag(detail_service.list_by_responden(responden_id)[0])
    set_pagination_links(response, request, total, page.limit, page.offset)
    return Page[TiDetailRead](items=items, total=total, limit=page.limit, offset=page.offset)
