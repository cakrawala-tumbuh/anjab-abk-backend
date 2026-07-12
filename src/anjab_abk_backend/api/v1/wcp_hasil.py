"""Endpoint analisis dan hasil WCP."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from ...dependencies import (
    get_current_principal,
    get_wcp_instrumen_service,
    get_wcp_jawaban_service,
    get_wcp_responden_service,
    rate_limit,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse
from ...wcp.schemas.hasil import WcpHasilRead, WcpHasilRespondenRead
from ...wcp.services.analisis import compute_hasil, compute_hasil_responden
from ...wcp.services.instrumen import WcpInstrumenService
from ...wcp.services.jawaban import WcpJawabanService
from ...wcp.services.responden import WcpRespondenService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}


@router.post(
    "/analisis",
    response_model=WcpHasilRead,
    summary="Jalankan analisis WCP (CLOSED → ANALYZED)",
    operation_id="wcp_analisis",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE},
)
def run_analisis(
    instrumen_service: Annotated[WcpInstrumenService, Depends(get_wcp_instrumen_service)],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    jwb_service: Annotated[WcpJawabanService, Depends(get_wcp_jawaban_service)],
) -> WcpHasilRead:
    instrumen = instrumen_service.get()
    if instrumen.status not in ("CLOSED", "ANALYZED"):
        raise ValidationAppError(
            f"Analisis hanya dapat dijalankan saat instrumen berstatus CLOSED atau ANALYZED"
            f" (saat ini: {instrumen.status})."
        )

    responden_list = rsp_service.list_all()
    submitted = [r for r in responden_list if r.sudah_submit]

    if len(submitted) < instrumen.min_responden:
        raise ValidationAppError(
            f"Analisis membutuhkan minimal {instrumen.min_responden} responden yang sudah"
            f" submit, baru ada {len(submitted)}."
        )

    responden_raw: list[tuple[str, dict[str, int]]] = [
        (r.id, jwb_service.get_raw_by_responden(r.id)) for r in submitted
    ]

    if instrumen.status == "CLOSED":
        instrumen_service.set_analyzed()

    return compute_hasil(responden_raw)


@router.get(
    "/hasil",
    response_model=WcpHasilRead,
    summary="Lihat hasil analisis instrumen WCP",
    operation_id="wcp_hasil",
)
def get_hasil(
    instrumen_service: Annotated[WcpInstrumenService, Depends(get_wcp_instrumen_service)],
    rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    jwb_service: Annotated[WcpJawabanService, Depends(get_wcp_jawaban_service)],
) -> WcpHasilRead:
    instrumen = instrumen_service.get()
    if instrumen.status != "ANALYZED":
        raise ValidationAppError(
            f"Hasil hanya tersedia setelah analisis dijalankan"
            f" (status saat ini: {instrumen.status})."
        )
    responden_list = rsp_service.list_all()
    submitted = [r for r in responden_list if r.sudah_submit]
    responden_raw: list[tuple[str, dict[str, int]]] = [
        (r.id, jwb_service.get_raw_by_responden(r.id)) for r in submitted
    ]
    return compute_hasil(responden_raw)


@router.get(
    "/hasil-responden/{responden_id}",
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
