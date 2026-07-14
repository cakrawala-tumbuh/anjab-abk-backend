"""Endpoint himpunan task terpilih & analisis/hasil Task Inventory."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    READ_GUARDS,
    authorize_sesi_access,
    get_current_principal,
    get_partisipan_service,
    get_ti_catalog_service,
    get_ti_detail_service,
    get_ti_responden_service,
    get_ti_seleksi_service,
    get_ti_sesi_service,
    rate_limit,
    require_admin,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...taskinv.schemas.catalog import TiCatalogRead
from ...taskinv.schemas.hasil import TiHasilSesiRead, TiTaskTerpilihRead
from ...taskinv.services.analisis import compute_hasil_sesi, compute_task_terpilih
from ...taskinv.services.catalog import TiCatalogService
from ...taskinv.services.detail import TiDetailService
from ...taskinv.services.responden import TiRespondenService
from ...taskinv.services.seleksi import TiSeleksiService
from ...taskinv.services.sesi import TiSesiService

router = APIRouter()

_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan admin."}}
_FORBIDDEN_PESERTA = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau peserta sesi."}
}


def _catalog_map(catalog: TiCatalogService, kodes: list[str]) -> dict[str, TiCatalogRead]:
    result: dict[str, TiCatalogRead] = {}
    for kode in kodes:
        try:
            result[kode] = catalog.get(kode)
        except Exception:  # noqa: BLE001 — kode usang diabaikan dari label
            continue
    return result


@router.get(
    "/{sesi_id}/task-terpilih",
    response_model=list[TiTaskTerpilihRead],
    summary="Himpunan task relevan yang dibekukan (tersedia setelah TAHAP2) (admin/peserta)",
    operation_id="taskinv_task_terpilih",
    dependencies=READ_GUARDS,
    responses={
        **_RATE,
        **_AUTH,
        **_FORBIDDEN_PESERTA,
        **_NOT_FOUND_SESI,
        422: {"model": ErrorResponse},
    },
)
def get_task_terpilih(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    seleksi_service: Annotated[TiSeleksiService, Depends(get_ti_seleksi_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    catalog: Annotated[TiCatalogService, Depends(get_ti_catalog_service)],
) -> list[TiTaskTerpilihRead]:
    sesi = sesi_service.get(sesi_id)
    authorize_sesi_access(principal, sesi, par_service, rsp_service)
    if sesi.status not in ("TAHAP3", "CLOSED", "ANALYZED"):
        raise ValidationAppError(
            f"Himpunan task terpilih baru tersedia setelah TAHAP3 (saat ini: {sesi.status})."
        )
    kodes = sesi_service.get_task_terpilih(sesi_id)
    counts = seleksi_service.count_relevan_per_task(sesi_id)
    n_tahap1 = rsp_service.count_tahap1_submitted(sesi_id)
    return compute_task_terpilih(kodes, _catalog_map(catalog, kodes), counts, n_tahap1)


@router.post(
    "/{sesi_id}/analisis",
    response_model=TiHasilSesiRead,
    summary="Jalankan analisis Task Inventory (CLOSED → ANALYZED) (admin)",
    operation_id="taskinv_analisis_run",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_SESI,
        422: {"model": ErrorResponse},
    },
)
def run_analisis(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    seleksi_service: Annotated[TiSeleksiService, Depends(get_ti_seleksi_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    detail_service: Annotated[TiDetailService, Depends(get_ti_detail_service)],
    catalog: Annotated[TiCatalogService, Depends(get_ti_catalog_service)],
) -> TiHasilSesiRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status not in ("CLOSED", "ANALYZED"):
        raise ValidationAppError(
            f"Analisis hanya dapat dijalankan saat sesi berstatus CLOSED atau ANALYZED"
            f" (saat ini: {sesi.status})."
        )
    n_tahap3 = detail_service.count_responden_submitted(sesi_id)
    if n_tahap3 < 1:
        raise ValidationAppError(
            "Analisis membutuhkan minimal 1 responden yang sudah submit detail Tahap 3."
        )
    if sesi.status == "CLOSED":
        sesi = sesi_service.transition(sesi_id, "ANALYZED")
    return _build_hasil(
        sesi, sesi_service, seleksi_service, rsp_service, detail_service, catalog, n_tahap3
    )


@router.get(
    "/{sesi_id}/hasil",
    response_model=TiHasilSesiRead,
    summary="Lihat hasil analisis sesi Task Inventory (admin)",
    operation_id="taskinv_hasil_get",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_SESI,
        422: {"model": ErrorResponse},
    },
)
def get_hasil(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    seleksi_service: Annotated[TiSeleksiService, Depends(get_ti_seleksi_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    detail_service: Annotated[TiDetailService, Depends(get_ti_detail_service)],
    catalog: Annotated[TiCatalogService, Depends(get_ti_catalog_service)],
) -> TiHasilSesiRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status != "ANALYZED":
        raise ValidationAppError(
            f"Hasil hanya tersedia setelah analisis dijalankan (status saat ini: {sesi.status})."
        )
    n_tahap3_g = detail_service.count_responden_submitted(sesi_id)
    return _build_hasil(
        sesi, sesi_service, seleksi_service, rsp_service, detail_service, catalog, n_tahap3_g
    )


def _build_hasil(
    sesi,  # noqa: ANN001 — TiSesiRead
    sesi_service: TiSesiService,
    seleksi_service: TiSeleksiService,
    rsp_service: TiRespondenService,
    detail_service: TiDetailService,
    catalog: TiCatalogService,
    n_tahap3: int | None = None,
) -> TiHasilSesiRead:
    kodes = sesi_service.get_task_terpilih(sesi.id)
    counts = seleksi_service.count_relevan_per_task(sesi.id)
    n_tahap1 = rsp_service.count_tahap1_submitted(sesi.id)
    details = detail_service.list_by_sesi(sesi.id)
    if n_tahap3 is None:
        n_tahap3 = detail_service.count_responden_submitted(sesi.id)
    return compute_hasil_sesi(
        sesi,
        kodes,
        _catalog_map(catalog, kodes),
        counts,
        n_tahap1,
        details,
        n_tahap3,
    )
