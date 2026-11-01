"""Endpoint baca riwayat perubahan redesain (read-model, append-only; khusus `tim-kajian`)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ...dependencies import (
    READ_GUARDS,
    Pagination,
    get_riwayat_service,
    pagination_params,
    require_tim_kajian,
)
from ...redesain.schemas.riwayat import RiwayatRead
from ...redesain.services.riwayat import RiwayatService
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest

router = APIRouter()

_GUARDS = [*READ_GUARDS, Depends(require_tim_kajian)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}


@router.get(
    "",
    response_model=Page[RiwayatRead],
    summary="Daftar riwayat perubahan redesain (tim-kajian)",
    operation_id="redesain_riwayat_list",
    dependencies=_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_riwayat(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[RiwayatService, Depends(get_riwayat_service)],
    entitas: Annotated[str | None, Query(description="Saring menurut nama entitas.")] = None,
    entitas_id: Annotated[str | None, Query(description="Saring menurut ID entitas.")] = None,
) -> Page[RiwayatRead]:
    """Daftar riwayat perubahan (terbaru dulu), opsional disaring entitas/entitas_id."""
    items, total = service.list(
        entitas=entitas, entitas_id=entitas_id, limit=page.limit, offset=page.offset
    )
    return Page[RiwayatRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "/search",
    response_model=Page[RiwayatRead],
    summary="Cari riwayat perubahan redesain (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_riwayat_search",
    dependencies=_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_riwayat(
    req: SearchRequest,
    service: Annotated[RiwayatService, Depends(get_riwayat_service)],
) -> Page[RiwayatRead]:
    """Cari riwayat dengan domain ala Odoo; field di-whitelist, nilai bound parameter."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[RiwayatRead](items=items, total=total, limit=req.limit, offset=req.offset)
