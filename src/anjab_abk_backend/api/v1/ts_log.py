"""Endpoint resource `TsLog` (log harian Time Study)."""

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
    get_ts_log_service,
    get_ts_penugasan_service,
    pagination_params,
    rate_limit,
)
from ...errors import NotFoundError, ValidationAppError
from ...schemas.common import ErrorResponse, Page
from ...security import Principal
from ...ts.schemas.log import TsLogCreate, TsLogRead, TsLogUpdate
from ...ts.schemas.penugasan import TsPenugasanRead
from ...ts.services.log import TsLogService
from ...ts.services.penugasan import TsPenugasanService
from ..pagination import set_pagination_links

router = APIRouter()

_AUTH_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND_PNG = {404: {"model": ErrorResponse, "description": "Penugasan tidak ditemukan."}}
_NOT_FOUND_LOG = {404: {"model": ErrorResponse, "description": "Log tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_INACTIVE = {422: {"model": ErrorResponse, "description": "Penugasan sedang tidak aktif."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik penugasan."}
}


def _authorize_penugasan(
    penugasan_id: str,
    png_service: TsPenugasanService,
    principal: Principal,
    par_service: PartisipanService,
) -> TsPenugasanRead:
    """Validasi penugasan ada & pemanggil admin/pemilik (partisipan penugasan ini)."""
    penugasan = png_service.get(penugasan_id)
    authorize_responden_access(principal, penugasan.partisipan_id, par_service)
    return penugasan


def _require_active(
    penugasan_id: str,
    png_service: TsPenugasanService,
    principal: Principal,
    par_service: PartisipanService,
) -> str:
    """Validasi penugasan ada, aktif, & milik pemanggil; kembalikan `partisipan_id`-nya."""
    penugasan = _authorize_penugasan(penugasan_id, png_service, principal, par_service)
    if not penugasan.aktif:
        raise ValidationAppError(
            f"Penugasan '{penugasan_id}' sedang tidak aktif; pencatatan log ditolak."
        )
    return penugasan.partisipan_id


@router.get(
    "/{penugasan_id}/log",
    response_model=Page[TsLogRead],
    summary="Daftar log harian penugasan Time Study (admin atau pemilik)",
    operation_id="ts_log_list",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND_PNG},
)
def list_log(
    penugasan_id: Annotated[str, Path(description="ID penugasan Time Study.")],
    request: Request,
    response: Response,
    page: Annotated[Pagination, Depends(pagination_params)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    png_service: Annotated[TsPenugasanService, Depends(get_ts_penugasan_service)],
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> Page[TsLogRead]:
    penugasan = _authorize_penugasan(penugasan_id, png_service, principal, par_service)
    items, total = log_service.list_by_partisipan(
        penugasan.partisipan_id, limit=page.limit, offset=page.offset
    )
    set_pagination_links(response, request, total, page.limit, page.offset)
    return Page[TsLogRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "/{penugasan_id}/log",
    response_model=TsLogRead,
    status_code=status.HTTP_201_CREATED,
    summary="Tambah log harian untuk penugasan Time Study (admin atau pemilik)",
    operation_id="ts_log_create",
    dependencies=[Depends(rate_limit)],
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_PNG,
        **_INACTIVE,
        409: {"model": ErrorResponse, "description": "Log untuk tanggal ini sudah ada."},
    },
)
def create_log(
    penugasan_id: Annotated[str, Path(description="ID penugasan Time Study.")],
    payload: TsLogCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    png_service: Annotated[TsPenugasanService, Depends(get_ts_penugasan_service)],
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> TsLogRead:
    partisipan_id = _require_active(penugasan_id, png_service, principal, par_service)
    return log_service.create(partisipan_id, payload)


@router.get(
    "/{penugasan_id}/log/{log_id}",
    response_model=TsLogRead,
    summary="Ambil detail log harian Time Study (admin atau pemilik)",
    operation_id="ts_log_get",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND_LOG},
)
def get_log(
    penugasan_id: Annotated[str, Path(description="ID penugasan Time Study.")],
    log_id: Annotated[str, Path(description="ID log.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    png_service: Annotated[TsPenugasanService, Depends(get_ts_penugasan_service)],
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> TsLogRead:
    penugasan = _authorize_penugasan(penugasan_id, png_service, principal, par_service)
    log = log_service.get(log_id)
    if log.partisipan_id != penugasan.partisipan_id:
        raise NotFoundError("Log tidak ditemukan untuk penugasan ini.")
    return log


@router.patch(
    "/{penugasan_id}/log/{log_id}",
    response_model=TsLogRead,
    summary="Perbarui log harian Time Study (admin atau pemilik)",
    operation_id="ts_log_update",
    dependencies=[Depends(rate_limit)],
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND_LOG, **_NOT_FOUND_PNG, **_INACTIVE},
)
def update_log(
    penugasan_id: Annotated[str, Path(description="ID penugasan Time Study.")],
    log_id: Annotated[str, Path(description="ID log.")],
    payload: TsLogUpdate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    png_service: Annotated[TsPenugasanService, Depends(get_ts_penugasan_service)],
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> TsLogRead:
    partisipan_id = _require_active(penugasan_id, png_service, principal, par_service)
    log = log_service.get(log_id)
    if log.partisipan_id != partisipan_id:
        raise NotFoundError("Log tidak ditemukan untuk penugasan ini.")
    return log_service.update(log_id, payload)
