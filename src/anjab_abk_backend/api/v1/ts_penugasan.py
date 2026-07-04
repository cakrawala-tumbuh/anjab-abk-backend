"""Endpoint resource `TsPenugasan`: assign partisipan ke Time Study."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    Pagination,
    authorize_responden_access,
    get_current_principal,
    get_partisipan_service,
    get_ts_penugasan_service,
    pagination_params,
    rate_limit,
    require_admin,
)
from ...schemas.common import ErrorResponse, Page
from ...security import Principal
from ...ts.schemas.penugasan import TsPenugasanCreate, TsPenugasanRead, TsPenugasanUpdate
from ...ts.services.penugasan import TsPenugasanService

router = APIRouter()

_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Penugasan Time Study tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik penugasan."}
}


@router.get(
    "",
    response_model=Page[TsPenugasanRead],
    summary="Daftar penugasan Time Study (admin)",
    operation_id="ts_penugasan_list",
    dependencies=[Depends(require_admin)],
    responses={**_AUTH, **_FORBIDDEN},
)
def list_penugasan(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[TsPenugasanService, Depends(get_ts_penugasan_service)],
) -> Page[TsPenugasanRead]:
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[TsPenugasanRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=TsPenugasanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Tugaskan partisipan ke Time Study (admin)",
    operation_id="ts_penugasan_create",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {
            "model": ErrorResponse,
            "description": "Partisipan sudah memiliki penugasan Time Study.",
        },
    },
)
def create_penugasan(
    payload: TsPenugasanCreate,
    service: Annotated[TsPenugasanService, Depends(get_ts_penugasan_service)],
) -> TsPenugasanRead:
    return service.create(payload)


@router.get(
    "/{penugasan_id}",
    response_model=TsPenugasanRead,
    summary="Ambil penugasan Time Study (admin atau pemilik)",
    operation_id="ts_penugasan_get",
    responses={**_AUTH, **_FORBIDDEN, **_NOT_FOUND},
)
def get_penugasan(
    penugasan_id: Annotated[str, Path(description="ID penugasan Time Study.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[TsPenugasanService, Depends(get_ts_penugasan_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> TsPenugasanRead:
    penugasan = service.get(penugasan_id)
    authorize_responden_access(principal, penugasan.partisipan_id, par_service)
    return penugasan


@router.patch(
    "/{penugasan_id}",
    response_model=TsPenugasanRead,
    summary="Perbarui penugasan Time Study (admin; mis. nonaktifkan)",
    operation_id="ts_penugasan_update",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND},
)
def update_penugasan(
    penugasan_id: Annotated[str, Path(description="ID penugasan Time Study.")],
    payload: TsPenugasanUpdate,
    service: Annotated[TsPenugasanService, Depends(get_ts_penugasan_service)],
) -> TsPenugasanRead:
    return service.update(penugasan_id, payload)


@router.delete(
    "/{penugasan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus penugasan Time Study (admin)",
    operation_id="ts_penugasan_delete",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND},
)
def delete_penugasan(
    penugasan_id: Annotated[str, Path(description="ID penugasan Time Study.")],
    service: Annotated[TsPenugasanService, Depends(get_ts_penugasan_service)],
) -> Response:
    service.delete(penugasan_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
