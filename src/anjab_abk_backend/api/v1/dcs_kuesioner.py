"""Endpoint kuesioner DCS untuk partisipan yang sedang login."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.services.partisipan import PartisipanService
from ...dcs.schemas.kuesioner import DcsKuesionerItemRead
from ...dcs.services.instrumen import DcsInstrumenService
from ...dcs.services.responden import DcsRespondenService
from ...dependencies import (
    READ_GUARDS,
    get_current_principal,
    get_dcs_instrumen_service,
    get_dcs_responden_service,
    get_partisipan_service,
)
from ...schemas.common import ErrorResponse
from ...security import Principal

router = APIRouter()

_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}


@router.get(
    "/kuesioner/saya",
    response_model=list[DcsKuesionerItemRead],
    summary="Daftar kuesioner DCS milik pengguna yang sedang login",
    operation_id="dcs_kuesioner_saya",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH},
)
def kuesioner_saya(
    principal: Annotated[Principal, Depends(get_current_principal)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    instrumen_service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
) -> list[DcsKuesionerItemRead]:
    """Kembalikan kuesioner DCS yang sudah di-assign ke partisipan, bila instrumen OPEN.

    Partisipan hanya melihat kuesioner DCS yang telah di-assign secara eksplisit
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
            DcsKuesionerItemRead(
                id=rsp.id,
                catatan=instrumen.catatan,
                sudah_submit=rsp.sudah_submit,
                submitted_at=rsp.submitted_at,
                created_at=rsp.created_at,
                instrumen_status=instrumen.status,
            )
        )
    return result
