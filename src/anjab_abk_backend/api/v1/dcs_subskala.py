"""Endpoint master data DCS: sub-skala dan item (read-only)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from ...dcs.schemas.subskala import DcsItemRead, DcsSubSkalaRead, DcsSubSkalaWithItemsRead
from ...dcs.services.subskala import DcsSubSkalaService
from ...dependencies import get_dcs_subskala_service
from ...schemas.common import ErrorResponse

router = APIRouter()

_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Sub-skala tidak ditemukan."}}


@router.get(
    "",
    response_model=list[DcsSubSkalaRead],
    summary="Daftar 3 sub-skala DCS",
    operation_id="dcs_subskala_list",
)
def list_sub_skala(
    service: Annotated[DcsSubSkalaService, Depends(get_dcs_subskala_service)],
) -> list[DcsSubSkalaRead]:
    return service.list_sub_skala()


@router.get(
    "/{kode}",
    response_model=DcsSubSkalaWithItemsRead,
    summary="Ambil sub-skala DCS beserta 14 item-nya",
    operation_id="dcs_subskala_get",
    responses=_NOT_FOUND,
)
def get_sub_skala(
    kode: Annotated[str, Path(description="Kode sub-skala (DEMAND/CONTROL/SUPPORT).")],
    service: Annotated[DcsSubSkalaService, Depends(get_dcs_subskala_service)],
) -> DcsSubSkalaWithItemsRead:
    return service.get_sub_skala(kode.upper())


@router.get(
    "/{kode}/items",
    response_model=list[DcsItemRead],
    summary="Daftar item untuk satu sub-skala DCS",
    operation_id="dcs_subskala_items",
    responses=_NOT_FOUND,
)
def list_items_by_sub_skala(
    kode: Annotated[str, Path(description="Kode sub-skala.")],
    service: Annotated[DcsSubSkalaService, Depends(get_dcs_subskala_service)],
) -> list[DcsItemRead]:
    sk = service.get_sub_skala(kode.upper())
    return sk.items
