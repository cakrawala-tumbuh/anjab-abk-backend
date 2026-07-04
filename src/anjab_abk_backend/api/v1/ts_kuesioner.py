"""Endpoint kuesioner Time Study untuk partisipan yang sedang login."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    get_current_principal,
    get_partisipan_service,
    get_ts_log_service,
    get_ts_penugasan_service,
)
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...ts.schemas.kuesioner import TsKuesionerItemRead
from ...ts.services.log import TsLogService
from ...ts.services.penugasan import TsPenugasanService

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
    png_service: Annotated[TsPenugasanService, Depends(get_ts_penugasan_service)],
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
) -> list[TsKuesionerItemRead]:
    """Kembalikan penugasan Time Study yang aktif milik partisipan yang sedang login.

    Partisipan hanya melihat penugasan yang telah di-assign secara eksplisit oleh
    admin dan sedang berstatus aktif. Tidak ada enrollment otomatis.
    """
    par = par_service.get_by_subject(principal.subject)
    if par is None:
        return []

    penugasan = png_service.get_by_partisipan(par.id)
    if penugasan is None or not penugasan.aktif:
        return []

    jumlah_log = log_service.count_by_partisipan(par.id)
    return [
        TsKuesionerItemRead(
            id=penugasan.id,
            aktif=penugasan.aktif,
            jumlah_log=jumlah_log,
            created_at=penugasan.created_at,
        )
    ]
