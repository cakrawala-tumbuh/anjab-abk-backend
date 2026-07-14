"""Endpoint seleksi relevansi Tahap 1 (per responden)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    READ_GUARDS,
    authorize_responden_access,
    get_current_principal,
    get_partisipan_service,
    get_ti_catalog_service,
    get_ti_responden_service,
    get_ti_seleksi_service,
    get_ti_sesi_service,
    rate_limit,
)
from ...errors import NotFoundError, ValidationAppError
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...taskinv.schemas.seleksi import TiSeleksiDraftSave, TiSeleksiRead
from ...taskinv.services.catalog import TiCatalogService
from ...taskinv.services.responden import TiRespondenService
from ...taskinv.services.seleksi import TiSeleksiService
from ...taskinv.services.sesi import TiSesiService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik responden."}
}


@router.put(
    "/responden/{responden_id}/seleksi",
    response_model=TiSeleksiRead,
    summary="Simpan draft seleksi relevansi Tahap 1 untuk satu responden (full-replace)",
    operation_id="taskinv_seleksi_save_draft",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_RSP,
        422: {
            "model": ErrorResponse,
            "description": "Kode task tidak valid, sesi bukan TAHAP1, atau responden sudah submit.",
        },
    },
)
def save_draft_seleksi(
    responden_id: Annotated[str, Path(description="ID responden.")],
    payload: TiSeleksiDraftSave,
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    seleksi_service: Annotated[TiSeleksiService, Depends(get_ti_seleksi_service)],
    catalog: Annotated[TiCatalogService, Depends(get_ti_catalog_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> TiSeleksiRead:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    sesi = sesi_service.get(responden.sesi_id)
    if sesi.status != "TAHAP1":
        raise ValidationAppError(
            f"Seleksi Tahap 1 hanya dapat disimpan saat sesi berstatus TAHAP1"
            f" (saat ini: {sesi.status})."
        )
    if responden.tahap1_submit:
        raise ValidationAppError(
            "Responden ini sudah menyelesaikan Tahap 1; draft tidak bisa diubah."
        )
    valid = catalog.valid_kodes_for_jabatan(sesi.jabatan_id)
    return seleksi_service.save_draft(responden_id, sesi.id, payload.task_kode, valid)


@router.post(
    "/responden/{responden_id}/seleksi/submit",
    response_model=TiSeleksiRead,
    status_code=status.HTTP_201_CREATED,
    summary="Finalisasi (submit) seleksi relevansi Tahap 1 tersimpan untuk satu responden",
    operation_id="taskinv_seleksi_submit",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_RSP,
        422: {
            "model": ErrorResponse,
            "description": (
                "Sesi bukan TAHAP1, responden sudah submit, atau belum ada task terpilih."
            ),
        },
    },
)
def submit_seleksi(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    seleksi_service: Annotated[TiSeleksiService, Depends(get_ti_seleksi_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> TiSeleksiRead:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    sesi = sesi_service.get(responden.sesi_id)
    if sesi.status != "TAHAP1":
        raise ValidationAppError(
            f"Seleksi Tahap 1 hanya dapat disubmit saat sesi berstatus TAHAP1"
            f" (saat ini: {sesi.status})."
        )
    if responden.tahap1_submit:
        raise ValidationAppError("Responden ini sudah menyelesaikan Tahap 1.")
    result = seleksi_service.submit(responden_id)
    rsp_service.mark_tahap1(responden_id)
    return result


@router.get(
    "/responden/{responden_id}/seleksi",
    response_model=TiSeleksiRead,
    summary="Lihat seleksi Tahap 1 satu responden (admin atau pemilik)",
    operation_id="taskinv_seleksi_get",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def get_seleksi(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    seleksi_service: Annotated[TiSeleksiService, Depends(get_ti_seleksi_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> TiSeleksiRead:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    result = seleksi_service.get_by_responden(responden_id)
    if result is None:
        raise NotFoundError("Responden belum submit seleksi Tahap 1.")
    return result
