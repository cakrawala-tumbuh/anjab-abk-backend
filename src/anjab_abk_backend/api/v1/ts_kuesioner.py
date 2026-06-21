"""Endpoint kuesioner Time Study untuk partisipan yang sedang login."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    get_current_principal,
    get_partisipan_service,
    get_ts_log_service,
    get_ts_responden_service,
    get_ts_sesi_service,
)
from ...errors import NotFoundError
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...ts.schemas.kuesioner import TsKuesionerItemRead
from ...ts.services.log import TsLogService
from ...ts.services.responden import TsRespondenService
from ...ts.services.sesi import TsSesiService

router = APIRouter()

_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}


@router.get(
    "/kuesioner/saya",
    response_model=list[TsKuesionerItemRead],
    summary="Daftar kuesioner Time Study milik pengguna yang sedang login",
    operation_id="ts_kuesioner_saya",
    responses=_AUTH,
)
def kuesioner_saya(
    principal: Annotated[Principal, Depends(get_current_principal)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    rsp_service: Annotated[TsRespondenService, Depends(get_ts_responden_service)],
    sesi_service: Annotated[TsSesiService, Depends(get_ts_sesi_service)],
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
) -> list[TsKuesionerItemRead]:
    """Kembalikan sesi Time Study yang sudah di-assign ke partisipan dan berstatus OPEN.

    Partisipan hanya melihat kuesioner Time Study yang telah di-assign secara eksplisit
    oleh admin (record responden sudah dibuat dengan ``partisipan_id`` mereka).
    Tidak ada enrollment otomatis.
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
        jumlah_log = log_service.count_by_responden(rsp.id)
        result.append(
            TsKuesionerItemRead(
                id=rsp.id,
                sesi_id=rsp.sesi_id,
                jabatan_label=rsp.jabatan_label,
                created_at=rsp.created_at,
                sesi_status=sesi.status,
                sesi_periode=sesi.periode,
                sesi_jabatan_id=sesi.jabatan_id,
                jumlah_log=jumlah_log,
            )
        )
    return result
