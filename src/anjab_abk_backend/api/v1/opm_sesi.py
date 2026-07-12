"""Endpoint resource `OpmSesi`: CRUD + transisi status + snapshot task."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Response, status

from ...dependencies import (
    Idempotency,
    Pagination,
    get_current_principal,
    get_opm_sesi_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_admin,
)
from ...errors import ConflictError
from ...opm.schemas.sesi import OpmSesiCreate, OpmSesiRead, OpmSesiTaskRead, OpmSesiUpdate
from ...opm.services.sesi import OpmSesiService
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Sesi OPM tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan admin."}}


@router.get(
    "",
    response_model=Page[OpmSesiRead],
    summary="Daftar sesi OPM",
    operation_id="opm_sesi_list",
)
def list_sesi(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
) -> Page[OpmSesiRead]:
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[OpmSesiRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=OpmSesiRead,
    status_code=status.HTTP_201_CREATED,
    summary="Buat sesi OPM (snapshot task dari sesi Task Inventory yang sudah frozen)",
    operation_id="opm_sesi_create",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        409: {"model": ErrorResponse, "description": "Jabatan sudah punya sesi OPM."},
        422: {
            "model": ErrorResponse,
            "description": (
                "Jabatan/SME panel/sesi Task Inventory tidak valid, atau belum frozen."
            ),
        },
    },
)
def create_sesi(
    payload: Annotated[
        OpmSesiCreate,
        Body(
            openapi_examples={
                "contoh": {
                    "summary": "Sesi OPM 2026-06",
                    "value": {
                        "jabatan_id": "jbt_a1b2c3d4",
                        "ti_sesi_id": "tises_a1b2c3d4",
                        "periode": "2026-06",
                        "min_responden": 3,
                        "max_responden": 10,
                    },
                }
            }
        ),
    ],
    service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> OpmSesiRead:
    cached = idem.cached()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        return OpmSesiRead.model_validate(cached)
    if not idem.reserve():
        raise ConflictError("Permintaan dengan Idempotency-Key ini sedang diproses.")
    try:
        item = service.create(payload)
    except Exception:
        idem.release()
        raise
    idem.remember(item)
    return item


@router.post(
    "/search",
    response_model=Page[OpmSesiRead],
    summary="Cari sesi OPM (domain ala Odoo)",
    operation_id="opm_sesi_search",
    responses={422: {"model": ErrorResponse, "description": "Domain/field tidak valid."}},
)
def search_sesi(
    req: SearchRequest,
    service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
) -> Page[OpmSesiRead]:
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[OpmSesiRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{sesi_id}",
    response_model=OpmSesiRead,
    summary="Ambil sesi OPM",
    operation_id="opm_sesi_get",
    responses=_NOT_FOUND,
)
def get_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
) -> OpmSesiRead:
    return service.get(sesi_id)


@router.patch(
    "/{sesi_id}",
    response_model=OpmSesiRead,
    summary="Perbarui sesi OPM (hanya saat DRAFT)",
    operation_id="opm_sesi_update",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def update_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    payload: OpmSesiUpdate,
    service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
) -> OpmSesiRead:
    return service.update(sesi_id, payload)


@router.delete(
    "/{sesi_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus sesi OPM (hanya saat DRAFT)",
    operation_id="opm_sesi_delete",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND},
)
def delete_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
) -> Response:
    service.delete(sesi_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{sesi_id}/buka",
    response_model=OpmSesiRead,
    summary="Buka sesi OPM (DRAFT → OPEN)",
    operation_id="opm_sesi_buka",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def buka_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
) -> OpmSesiRead:
    return service.transition(sesi_id, "OPEN")


@router.post(
    "/{sesi_id}/tutup",
    response_model=OpmSesiRead,
    summary="Tutup sesi OPM (OPEN → CLOSED)",
    operation_id="opm_sesi_tutup",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def tutup_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
) -> OpmSesiRead:
    return service.transition(sesi_id, "CLOSED")


@router.get(
    "/{sesi_id}/task",
    response_model=list[OpmSesiTaskRead],
    summary="Daftar snapshot task dalam sesi OPM",
    operation_id="opm_sesi_task_list",
    responses=_NOT_FOUND,
)
def list_task(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
) -> list[OpmSesiTaskRead]:
    service.get(sesi_id)
    return service.list_task(sesi_id)
