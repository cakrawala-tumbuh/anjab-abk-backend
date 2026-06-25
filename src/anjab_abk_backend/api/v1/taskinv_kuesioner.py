"""Endpoint kuesioner Task Inventory untuk partisipan yang sedang login."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    get_current_principal,
    get_partisipan_service,
    get_ti_responden_service,
    get_ti_sesi_service,
)
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...taskinv.schemas.kuesioner import TiKuesionerItemRead
from ...taskinv.services.responden import TiRespondenService
from ...taskinv.services.sesi import TiSesiService

router = APIRouter()

_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}

_ACTIVE_STATUSES = ["TAHAP1", "TAHAP2", "TAHAP3"]


@router.get(
    "/kuesioner/saya",
    response_model=list[TiKuesionerItemRead],
    summary="Daftar kuesioner Task Inventory milik pengguna yang sedang login",
    operation_id="taskinv_kuesioner_saya",
    responses=_AUTH,
)
def kuesioner_saya(
    principal: Annotated[Principal, Depends(get_current_principal)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
) -> list[TiKuesionerItemRead]:
    """Enrollment otomatis: Task Inventory bersifat universal — tiap partisipan
    mengisi SEMUA sesi aktif (TAHAP1/TAHAP2/TAHAP3), sambil membuat record
    responden bila belum ada.
    """
    par = par_service.get_by_subject(principal.subject)
    if par is None:
        return []

    sesi_list, _ = sesi_service.search(
        domain=[("status", "in", _ACTIVE_STATUSES)],
        order=[("created_at", "desc")],
        limit=100,
        offset=0,
    )

    result = []
    for sesi in sesi_list:
        rsp = rsp_service.ensure_for_partisipan(
            sesi.id,
            partisipan_id=par.id,
            nama=par.nama,
        )
        result.append(
            TiKuesionerItemRead(
                id=rsp.id,
                sesi_id=rsp.sesi_id,
                tahap1_submit=rsp.tahap1_submit,
                tahap1_submitted_at=rsp.tahap1_submitted_at,
                tahap3_submit=rsp.tahap3_submit,
                tahap3_submitted_at=rsp.tahap3_submitted_at,
                created_at=rsp.created_at,
                sesi_status=sesi.status,
                sesi_jabatan_id=sesi.jabatan_id,
                sesi_periode=sesi.periode,
            )
        )
    return result
