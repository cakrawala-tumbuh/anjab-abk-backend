"""Endpoint resource `WcpSesi`: CRUD + transisi status."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Response, status

from ...dependencies import (
    Idempotency,
    Pagination,
    get_current_principal,
    get_wcp_sesi_service,
    idempotency,
    pagination_params,
    rate_limit,
)
from ...errors import ConflictError
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ...wcp.schemas.sesi import WcpSesiCreate, WcpSesiRead, WcpSesiUpdate
from ...wcp.services.sesi import WcpSesiService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Sesi WCP tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}


@router.get(
    "",
    response_model=Page[WcpSesiRead],
    summary="Daftar sesi WCP",
    operation_id="wcp_sesi_list",
)
def list_sesi(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[WcpSesiService, Depends(get_wcp_sesi_service)],
) -> Page[WcpSesiRead]:
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[WcpSesiRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=WcpSesiRead,
    status_code=status.HTTP_201_CREATED,
    summary="Buat sesi WCP",
    operation_id="wcp_sesi_create",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        409: {"model": ErrorResponse, "description": "Sesi untuk jabatan+periode sudah ada."},
    },
)
def create_sesi(
    payload: Annotated[
        WcpSesiCreate,
        Body(
            openapi_examples={
                "contoh": {
                    "summary": "Sesi WCP 2025-06",
                    "value": {
                        "periode": "2025-06",
                        "min_responden": 6,
                        "max_responden": 8,
                    },
                }
            }
        ),
    ],
    service: Annotated[WcpSesiService, Depends(get_wcp_sesi_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> WcpSesiRead:
    cached = idem.cached()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        return WcpSesiRead.model_validate(cached)
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
    response_model=Page[WcpSesiRead],
    summary="Cari sesi WCP (domain ala Odoo)",
    operation_id="wcp_sesi_search",
    responses={422: {"model": ErrorResponse, "description": "Domain/field tidak valid."}},
)
def search_sesi(
    req: SearchRequest,
    service: Annotated[WcpSesiService, Depends(get_wcp_sesi_service)],
) -> Page[WcpSesiRead]:
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[WcpSesiRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{sesi_id}",
    response_model=WcpSesiRead,
    summary="Ambil sesi WCP",
    operation_id="wcp_sesi_get",
    responses=_NOT_FOUND,
)
def get_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi WCP.")],
    service: Annotated[WcpSesiService, Depends(get_wcp_sesi_service)],
) -> WcpSesiRead:
    return service.get(sesi_id)


@router.patch(
    "/{sesi_id}",
    response_model=WcpSesiRead,
    summary="Perbarui sesi WCP (hanya saat DRAFT)",
    operation_id="wcp_sesi_update",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def update_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi WCP.")],
    payload: WcpSesiUpdate,
    service: Annotated[WcpSesiService, Depends(get_wcp_sesi_service)],
) -> WcpSesiRead:
    return service.update(sesi_id, payload)


@router.delete(
    "/{sesi_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus sesi WCP (hanya saat DRAFT)",
    operation_id="wcp_sesi_delete",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def delete_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi WCP.")],
    service: Annotated[WcpSesiService, Depends(get_wcp_sesi_service)],
) -> Response:
    service.delete(sesi_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{sesi_id}/buka",
    response_model=WcpSesiRead,
    summary="Buka sesi WCP (DRAFT → OPEN)",
    operation_id="wcp_sesi_buka",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def buka_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi WCP.")],
    service: Annotated[WcpSesiService, Depends(get_wcp_sesi_service)],
) -> WcpSesiRead:
    return service.transition(sesi_id, "OPEN")


@router.post(
    "/{sesi_id}/tutup",
    response_model=WcpSesiRead,
    summary="Tutup sesi WCP (OPEN → CLOSED)",
    operation_id="wcp_sesi_tutup",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def tutup_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi WCP.")],
    service: Annotated[WcpSesiService, Depends(get_wcp_sesi_service)],
) -> WcpSesiRead:
    return service.transition(sesi_id, "CLOSED")
