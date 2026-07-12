"""Endpoint catalog Task Inventory (master data, read-only + admin purge/reseed)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ...anjab.services.jabatan import JabatanService
from ...dependencies import (
    SessionDep,
    get_detil_tugas_service,
    get_jabatan_service,
    get_ti_catalog_service,
    get_ti_sesi_service,
    get_tugas_pokok_service,
    get_uraian_tugas_service,
    rate_limit,
    require_admin,
)
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...taskinv.schemas.catalog import (
    TiCatalogPurgeCounts,
    TiCatalogPurgeResult,
    TiCatalogRead,
    TiCatalogReseedCounts,
    TiCatalogReseedResult,
    TiKombinasiRead,
)
from ...taskinv.seed import seed_catalog_models
from ...taskinv.services.catalog import TiCatalogService
from ...taskinv.services.catalog_admin import guard_no_active_sesi, purge_catalog
from ...taskinv.services.detil_tugas import DetilTugasService
from ...taskinv.services.sesi import TiSesiService
from ...taskinv.services.tugas_pokok import TugasPokokService
from ...taskinv.services.uraian_tugas import UraianTugasService

router = APIRouter()

logger = logging.getLogger("anjab_abk_backend.api.v1.taskinv_catalog")

_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan admin."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}


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


@router.post(
    "/purge",
    response_model=TiCatalogPurgeResult,
    summary="Purge (hapus total) katalog master Task Inventory",
    operation_id="taskinv_catalog_purge",
    dependencies=[Depends(rate_limit)],
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {"model": ErrorResponse, "description": "Masih ada sesi Task Inventory aktif."},
    },
)
def purge_catalog_endpoint(
    session: SessionDep,
    sesi_svc: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    principal: Annotated[Principal, Depends(require_admin)],
) -> TiCatalogPurgeResult:
    guard_no_active_sesi(sesi_svc)
    logger.warning("catalog_purge", extra={"modul": "taskinv", "actor": principal.subject})
    return TiCatalogPurgeResult(deleted=TiCatalogPurgeCounts(**purge_catalog(session)))


@router.post(
    "/reseed",
    response_model=TiCatalogReseedResult,
    summary="Reseed katalog master Task Inventory dari task_catalog.json",
    operation_id="taskinv_catalog_reseed",
    dependencies=[Depends(rate_limit)],
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def reseed_catalog_endpoint(
    principal: Annotated[Principal, Depends(require_admin)],
    tp_svc: Annotated[TugasPokokService, Depends(get_tugas_pokok_service)],
    dt_svc: Annotated[DetilTugasService, Depends(get_detil_tugas_service)],
    ut_svc: Annotated[UraianTugasService, Depends(get_uraian_tugas_service)],
    jabatan_svc: Annotated[JabatanService, Depends(get_jabatan_service)],
) -> TiCatalogReseedResult:
    logger.warning("catalog_reseed", extra={"modul": "taskinv", "actor": principal.subject})
    counts = seed_catalog_models(tp_svc, dt_svc, ut_svc, jabatan_svc)
    return TiCatalogReseedResult(created=TiCatalogReseedCounts(**counts))
