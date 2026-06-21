"""Endpoint kuesioner DCS untuk partisipan yang sedang login."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.services.partisipan import PartisipanService
from ...dcs.schemas.kuesioner import DcsKuesionerItemRead
from ...dcs.services.responden import DcsRespondenService
from ...dcs.services.sesi import DcsSesiService
from ...dependencies import (
    get_current_principal,
    get_dcs_responden_service,
    get_dcs_sesi_service,
    get_partisipan_service,
)
from ...schemas.common import ErrorResponse
from ...security import Principal

router = APIRouter()

_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}


@router.get(
    "/kuesioner/saya",
    response_model=list[DcsKuesionerItemRead],
    summary="Daftar kuesioner DCS milik pengguna yang sedang login",
    operation_id="dcs_kuesioner_saya",
    responses=_AUTH,
)
def kuesioner_saya(
    principal: Annotated[Principal, Depends(get_current_principal)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    sesi_service: Annotated[DcsSesiService, Depends(get_dcs_sesi_service)],
) -> list[DcsKuesionerItemRead]:
    par = par_service.get_by_subject(principal.subject)
    if par is None:
        return []
    responden_list = rsp_service.list_by_partisipan(par.id)
    result = []
    for rsp in responden_list:
        try:
            sesi = sesi_service.get(rsp.sesi_id)
        except Exception:
            continue
        result.append(
            DcsKuesionerItemRead(
                id=rsp.id,
                sesi_id=rsp.sesi_id,
                jabatan_label=rsp.jabatan_label,
                sudah_submit=rsp.sudah_submit,
                submitted_at=rsp.submitted_at,
                created_at=rsp.created_at,
                sesi_status=sesi.status,
                sesi_periode=sesi.periode,
                sesi_jabatan_id=sesi.jabatan_id,
            )
        )
    return result
