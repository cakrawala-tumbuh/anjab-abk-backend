"""Endpoint kuesioner WCP untuk partisipan yang sedang login."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...anjab.services.jabatan import JabatanService
from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    get_current_principal,
    get_jabatan_service,
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
    jabatan_service: Annotated[JabatanService, Depends(get_jabatan_service)],
) -> list[WcpKuesionerItemRead]:
    """Enrollment otomatis: kembalikan sesi WCP yang berlaku untuk jabatan utama
    partisipan dan berstatus OPEN, sambil membuat record responden bila belum ada.

    Tiap partisipan mengisi tepat satu WCP sesuai ``jabatan_utama_id``-nya.
    """
    par = par_service.get_by_subject(principal.subject)
    if par is None:
        return []

    try:
        jabatan_label = jabatan_service.get(par.jabatan_utama_id).nama
    except Exception:
        jabatan_label = par.jabatan_utama_id

    sesi_list, _ = sesi_service.search(
        domain=[("jabatan_id", "=", par.jabatan_utama_id), ("status", "=", "OPEN")],
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
            jabatan_label=jabatan_label,
        )
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
