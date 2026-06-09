"""Endpoint master data WCP: dimensi dan item (read-only)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from ...dependencies import get_wcp_dimensi_service
from ...schemas.common import ErrorResponse
from ...wcp.schemas.dimensi import WcpDimensiRead, WcpDimensiWithItemsRead, WcpItemRead
from ...wcp.services.dimensi import WcpDimensiService

router = APIRouter()

_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Dimensi tidak ditemukan."}}


@router.get(
    "",
    response_model=list[WcpDimensiRead],
    summary="Daftar 12 dimensi WCP",
    operation_id="wcp_dimensi_list",
)
def list_dimensi(
    service: Annotated[WcpDimensiService, Depends(get_wcp_dimensi_service)],
) -> list[WcpDimensiRead]:
    return service.list_dimensi()


@router.get(
    "/{kode}",
    response_model=WcpDimensiWithItemsRead,
    summary="Ambil dimensi WCP beserta 6 item-nya",
    operation_id="wcp_dimensi_get",
    responses=_NOT_FOUND,
)
def get_dimensi(
    kode: Annotated[str, Path(description="Kode dimensi (SC/TM/AS/RC/DA/WP/PC/SS/CH/SD/PI/RA).")],
    service: Annotated[WcpDimensiService, Depends(get_wcp_dimensi_service)],
) -> WcpDimensiWithItemsRead:
    return service.get_dimensi(kode.upper())


@router.get(
    "/{kode}/items",
    response_model=list[WcpItemRead],
    summary="Daftar item untuk satu dimensi WCP",
    operation_id="wcp_dimensi_items",
    responses=_NOT_FOUND,
)
def list_items_by_dimensi(
    kode: Annotated[str, Path(description="Kode dimensi.")],
    service: Annotated[WcpDimensiService, Depends(get_wcp_dimensi_service)],
) -> list[WcpItemRead]:
    dim = service.get_dimensi(kode.upper())
    return dim.items
