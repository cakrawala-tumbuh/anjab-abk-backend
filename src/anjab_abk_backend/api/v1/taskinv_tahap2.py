"""Endpoint review koordinator Tahap 2 Task Inventory."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from ...dependencies import (
    get_current_principal,
    get_ti_catalog_service,
    get_ti_responden_service,
    get_ti_seleksi_service,
    get_ti_sesi_service,
    get_ti_tahap2_service,
    rate_limit,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse
from ...taskinv.schemas.tahap2 import TiTahap2ReviewRead, TiTahap2Submit
from ...taskinv.services.catalog import TiCatalogService
from ...taskinv.services.responden import TiRespondenService
from ...taskinv.services.seleksi import TiSeleksiService
from ...taskinv.services.sesi import TiSesiService
from ...taskinv.services.tahap2 import TiTahap2Service

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}


@router.get(
    "/{sesi_id}/tahap2",
    response_model=TiTahap2ReviewRead,
    summary="Lihat task yang perlu diputuskan koordinator di Tahap 2",
    operation_id="taskinv_tahap2_get",
    responses={**_NOT_FOUND_SESI, 422: {"model": ErrorResponse}},
)
def get_tahap2_review(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    seleksi_service: Annotated[TiSeleksiService, Depends(get_ti_seleksi_service)],
    tahap2_service: Annotated[TiTahap2Service, Depends(get_ti_tahap2_service)],
) -> TiTahap2ReviewRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status not in ("TAHAP2", "TAHAP3", "CLOSED", "ANALYZED"):
        raise ValidationAppError(
            f"Review Tahap 2 hanya tersedia setelah TAHAP2 (saat ini: {sesi.status})."
        )
    n_submitted = rsp_service.count_tahap1_submitted(sesi_id)
    partial = seleksi_service.partial_terpilih(sesi_id, n_submitted)
    counts = seleksi_service.count_relevan_per_task(sesi_id)
    return tahap2_service.get_review(sesi_id, partial, counts, n_submitted)


@router.post(
    "/{sesi_id}/tahap2",
    response_model=TiTahap2ReviewRead,
    summary="Submit keputusan koordinator untuk task-task Tahap 2",
    operation_id="taskinv_tahap2_submit",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_NOT_FOUND_SESI,
        422: {"model": ErrorResponse, "description": "Sesi bukan TAHAP2 / kode task tidak valid."},
    },
)
def submit_tahap2_keputusan(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    payload: TiTahap2Submit,
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    seleksi_service: Annotated[TiSeleksiService, Depends(get_ti_seleksi_service)],
    catalog: Annotated[TiCatalogService, Depends(get_ti_catalog_service)],
    tahap2_service: Annotated[TiTahap2Service, Depends(get_ti_tahap2_service)],
) -> TiTahap2ReviewRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status != "TAHAP2":
        raise ValidationAppError(
            f"Keputusan koordinator hanya dapat disubmit saat sesi berstatus TAHAP2"
            f" (saat ini: {sesi.status})."
        )
    n_submitted = rsp_service.count_tahap1_submitted(sesi_id)
    partial = seleksi_service.partial_terpilih(sesi_id, n_submitted)
    partial_set = set(partial)
    submitted_kodes = {k.task_kode for k in payload.keputusan}
    non_partial = submitted_kodes - partial_set
    if non_partial:
        raise ValidationAppError(
            f"Task berikut bukan task partial (sudah dipilih semua atau tidak ada di seleksi): "
            f"{', '.join(sorted(non_partial)[:5])}"
        )
    valid_kodes = catalog.valid_kodes(sesi.unit, sesi.kategori_jabatan)
    return tahap2_service.submit_keputusan(sesi_id, payload.keputusan, valid_kodes)
