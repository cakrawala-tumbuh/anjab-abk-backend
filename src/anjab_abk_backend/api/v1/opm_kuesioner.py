"""Endpoint kuesioner OPM untuk partisipan yang sedang login."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    get_current_principal,
    get_opm_responden_service,
    get_opm_sesi_service,
    get_partisipan_service,
)
from ...errors import NotFoundError
from ...opm.schemas.kuesioner import OpmKuesionerItemRead
from ...opm.services.responden import OpmRespondenService
from ...opm.services.sesi import OpmSesiService
from ...schemas.common import ErrorResponse
from ...security import Principal

router = APIRouter()

_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}


@router.get(
    "/kuesioner/saya",
    response_model=list[OpmKuesionerItemRead],
    summary="Daftar kuesioner OPM milik pengguna yang sedang login",
    operation_id="opm_kuesioner_saya",
    responses=_AUTH,
)
def kuesioner_saya(
    principal: Annotated[Principal, Depends(get_current_principal)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    sesi_service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
) -> list[OpmKuesionerItemRead]:
    """Kembalikan sesi OPM yang sudah di-assign ke partisipan dan berstatus OPEN.

    Partisipan hanya melihat kuesioner OPM yang telah di-assign secara eksplisit
    (record responden dibuat otomatis dari anggota SME panel saat sesi dibuat,
    atau ditambahkan manual admin).
    """
    par = par_service.get_by_subject(principal.subject)
    if par is None:
        return []

    result = []
    for rsp in rsp_service.list_by_partisipan(par.id):
        try:
            sesi = sesi_service.get(rsp.sesi_id)
        except NotFoundError:
            continue
        if sesi.status != "OPEN":
            continue
        result.append(
            OpmKuesionerItemRead(
                id=rsp.id,
                sesi_id=rsp.sesi_id,
                sesi_catatan=sesi.catatan,
                sudah_submit=rsp.sudah_submit,
                submitted_at=rsp.submitted_at,
                created_at=rsp.created_at,
                sesi_status=sesi.status,
                sesi_periode=sesi.periode,
            )
        )
    return result
