"""Endpoint analisis dan hasil OPM."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from ...dependencies import (
    get_opm_jawaban_service,
    get_opm_responden_service,
    get_opm_sesi_service,
    rate_limit,
    require_admin,
)
from ...errors import ValidationAppError
from ...opm.schemas.hasil import OpmHasilSesiRead
from ...opm.services.analisis import compute_hasil_sesi
from ...opm.services.jawaban import OpmJawabanService
from ...opm.services.responden import OpmRespondenService
from ...opm.services.sesi import OpmSesiService
from ...schemas.common import ErrorResponse

router = APIRouter()

_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi OPM tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan admin."}}


@router.post(
    "/{sesi_id}/analisis",
    response_model=OpmHasilSesiRead,
    summary="Jalankan analisis OPM (CLOSED → ANALYZED) (admin)",
    operation_id="opm_analisis_run",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_SESI,
        422: {
            "model": ErrorResponse,
            "description": "Sesi bukan CLOSED/ANALYZED, atau responden submit < min_responden.",
        },
    },
)
def run_analisis(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    sesi_service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    jwb_service: Annotated[OpmJawabanService, Depends(get_opm_jawaban_service)],
) -> OpmHasilSesiRead:
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

    tasks = sesi_service.list_task(sesi_id)
    responden_raw = [(r.id, jwb_service.get_raw_by_responden(r.id)) for r in submitted]

    if sesi.status == "CLOSED":
        sesi = sesi_service.transition(sesi_id, "ANALYZED")

    return compute_hasil_sesi(sesi, tasks, responden_raw)


@router.get(
    "/{sesi_id}/hasil",
    response_model=OpmHasilSesiRead,
    summary="Lihat hasil analisis sesi OPM (admin)",
    operation_id="opm_hasil_sesi_get",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_SESI,
        422: {"model": ErrorResponse, "description": "Sesi belum ANALYZED."},
    },
)
def get_hasil_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    sesi_service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    jwb_service: Annotated[OpmJawabanService, Depends(get_opm_jawaban_service)],
) -> OpmHasilSesiRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status != "ANALYZED":
        raise ValidationAppError(
            f"Hasil hanya tersedia setelah analisis dijalankan (status saat ini: {sesi.status})."
        )
    tasks = sesi_service.list_task(sesi_id)
    responden_list = rsp_service.list_by_sesi(sesi_id)
    submitted = [r for r in responden_list if r.sudah_submit]
    responden_raw = [(r.id, jwb_service.get_raw_by_responden(r.id)) for r in submitted]
    return compute_hasil_sesi(sesi, tasks, responden_raw)
