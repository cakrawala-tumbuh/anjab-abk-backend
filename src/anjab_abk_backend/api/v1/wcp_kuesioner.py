"""Endpoint kuesioner WCP untuk partisipan yang sedang login."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    get_current_principal,
    get_partisipan_service,
    get_wcp_instrumen_service,
    get_wcp_responden_service,
)
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...wcp.schemas.kuesioner import WcpKuesionerItemRead
from ...wcp.services.instrumen import WcpInstrumenService
from ...wcp.services.responden import WcpRespondenService

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
    instrumen_service: Annotated[WcpInstrumenService, Depends(get_wcp_instrumen_service)],
) -> list[WcpKuesionerItemRead]:
    """Kembalikan kuesioner WCP yang sudah di-assign ke partisipan, bila instrumen OPEN.

    Partisipan hanya melihat kuesioner WCP yang telah di-assign secara eksplisit
    oleh admin (record responden sudah dibuat dengan ``partisipan_id`` mereka).
    Tidak ada enrollment otomatis.
    """
    par = par_service.get_by_subject(principal.subject)
    if par is None:
        return []

    instrumen = instrumen_service.get()
    if instrumen.status != "OPEN":
        return []

    result = []
    for rsp in rsp_service.list_by_partisipan(par.id):
        result.append(
            WcpKuesionerItemRead(
                id=rsp.id,
                catatan=instrumen.catatan,
                sudah_submit=rsp.sudah_submit,
                submitted_at=rsp.submitted_at,
                created_at=rsp.created_at,
                instrumen_status=instrumen.status,
            )
        )
    return result
