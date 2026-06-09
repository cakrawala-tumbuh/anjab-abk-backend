"""Endpoint analisis dan hasil WCP."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from ...dependencies import (
    get_current_principal,
    get_wcp_jawaban_service,
    get_wcp_responden_service,
    get_wcp_sesi_service,
    rate_limit,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse
from ...wcp.schemas.hasil import WcpHasilRespondenRead, WcpHasilSesiRead
from ...wcp.services.analisis import compute_hasil_responden, compute_hasil_sesi
from ...wcp.services.jawaban import WcpJawabanService
from ...wcp.services.responden import WcpRespondenService
from ...wcp.services.sesi import WcpSesiService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi WCP tidak ditemukan."}}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}


@router.post(
    "/{sesi_id}/analisis",
    response_model=WcpHasilSesiRead,
    summary="Jalankan analisis WCP (CLOSED → ANALYZED)",
    operation_id="wcp_analisis_run",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND_SESI},
)
def run_analisis(
    sesi_id: Annotated[str, Path(description="ID sesi WCP.")],
    sesi_service: Annotated[WcpSesiService, Depends(get_wcp_sesi_service)],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    jwb_service: Annotated[WcpJawabanService, Depends(get_wcp_jawaban_service)],
) -> WcpHasilSesiRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status not in ("CLOSED", "ANALYZED"):
        raise ValidationAppError(
            f"Analisis hanya dapat dijalankan saat sesi berstatus CLOSED atau ANALYZED"
            f" (saat ini: {sesi.status})."
        )

    responden_list = rsp_service.list_by_sesi(sesi_id)
    submitted = [r for r in responden_list if r.sudah_submit]

    if len(submitted) < sesi.min_responden:
        raise ValidationAppError(
            f"Analisis membutuhkan minimal {sesi.min_responden} responden yang sudah submit,"
            f" baru ada {len(submitted)}."
        )

    responden_raw: list[tuple[str, dict[str, int]]] = [
        (r.id, jwb_service.get_raw_by_responden(r.id)) for r in submitted
    ]

    if sesi.status == "CLOSED":
        sesi_service.transition(sesi_id, "ANALYZED")

    return compute_hasil_sesi(sesi, responden_raw)


@router.get(
    "/{sesi_id}/hasil",
    response_model=WcpHasilSesiRead,
    summary="Lihat hasil analisis sesi WCP",
    operation_id="wcp_hasil_sesi_get",
    responses=_NOT_FOUND_SESI,
)
def get_hasil_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi WCP.")],
    sesi_service: Annotated[WcpSesiService, Depends(get_wcp_sesi_service)],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    jwb_service: Annotated[WcpJawabanService, Depends(get_wcp_jawaban_service)],
) -> WcpHasilSesiRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status != "ANALYZED":
        raise ValidationAppError(
            f"Hasil hanya tersedia setelah analisis dijalankan"
            f" (status saat ini: {sesi.status})."
        )
    responden_list = rsp_service.list_by_sesi(sesi_id)
    submitted = [r for r in responden_list if r.sudah_submit]
    responden_raw: list[tuple[str, dict[str, int]]] = [
        (r.id, jwb_service.get_raw_by_responden(r.id)) for r in submitted
    ]
    return compute_hasil_sesi(sesi, responden_raw)


@router.get(
    "/responden/{responden_id}/hasil",
    response_model=WcpHasilRespondenRead,
    summary="Lihat hasil analisis per responden",
    operation_id="wcp_hasil_responden_get",
    responses=_NOT_FOUND_RSP,
)
def get_hasil_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    jwb_service: Annotated[WcpJawabanService, Depends(get_wcp_jawaban_service)],
) -> WcpHasilRespondenRead:
    responden = rsp_service.get(responden_id)
    if not responden.sudah_submit:
        raise ValidationAppError("Responden belum mengirimkan jawaban.")
    raw = jwb_service.get_raw_by_responden(responden_id)
    return compute_hasil_responden(responden_id, raw)
