"""Endpoint kuesioner WCP untuk partisipan yang sedang login."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    get_current_principal,
    get_partisipan_service,
    get_wcp_responden_service,
    get_wcp_sesi_service,
)
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...wcp.schemas.kuesioner import WcpKuesionerItemRead
from ...wcp.services.responden import WcpRespondenService
from ...wcp.services.sesi import WcpSesiService

router = APIRouter()

_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}


@router.get(
    "/kuesioner/saya",
    response_model=list[WcpKuesionerItemRead],
    summary="Daftar kuesioner WCP milik pengguna yang sedang login",
    operation_id="wcp_kuesioner_saya",
    responses=_AUTH,
)
def kuesioner_saya(
    principal: Annotated[Principal, Depends(get_current_principal)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    sesi_service: Annotated[WcpSesiService, Depends(get_wcp_sesi_service)],
) -> list[WcpKuesionerItemRead]:
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
            WcpKuesionerItemRead(
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
