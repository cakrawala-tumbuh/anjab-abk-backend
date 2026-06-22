"""Endpoint catalog Task Inventory (master data, read-only)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ...dependencies import get_ti_catalog_service
from ...taskinv.schemas.catalog import TiCatalogRead, TiKombinasiRead
from ...taskinv.services.catalog import TiCatalogService

router = APIRouter()


@router.get(
    "/kombinasi",
    response_model=list[TiKombinasiRead],
    summary="Daftar kombinasi unit × jabatan beserta jumlah task",
    operation_id="taskinv_catalog_kombinasi",
)
def list_kombinasi(
    service: Annotated[TiCatalogService, Depends(get_ti_catalog_service)],
) -> list[TiKombinasiRead]:
    return service.list_kombinasi()


@router.get(
    "",
    response_model=list[TiCatalogRead],
    summary="Daftar task catalog untuk kombinasi unit × jabatan",
    operation_id="taskinv_catalog_list",
)
def list_catalog(
    service: Annotated[TiCatalogService, Depends(get_ti_catalog_service)],
    jabatan_id: Annotated[str, Query(description="ID jabatan.")],
    unit: Annotated[
        str | None,
        Query(
            description=(
                "Unit/jenjang (TK/SD/SMP/SMA). Opsional; bila tidak diisi, "
                "kembalikan semua task untuk jabatan ini lintas unit."
            )
        ),
    ] = None,
) -> list[TiCatalogRead]:
    if unit is not None:
        return service.list_by_kombinasi(unit, jabatan_id)
    return service.list_by_jabatan(jabatan_id)
