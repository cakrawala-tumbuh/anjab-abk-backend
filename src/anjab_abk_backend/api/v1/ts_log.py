"""Endpoint resource `TsLog` (log harian Time Study)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from ...dependencies import (
    get_current_principal,
    get_ts_log_service,
    get_ts_penugasan_service,
    rate_limit,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse
from ...ts.schemas.log import TsLogCreate, TsLogRead, TsLogUpdate
from ...ts.services.log import TsLogService
from ...ts.services.penugasan import TsPenugasanService

router = APIRouter()

_AUTH_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND_PNG = {404: {"model": ErrorResponse, "description": "Penugasan tidak ditemukan."}}
_NOT_FOUND_LOG = {404: {"model": ErrorResponse, "description": "Log tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_INACTIVE = {422: {"model": ErrorResponse, "description": "Penugasan sedang tidak aktif."}}


def _require_active(penugasan_id: str, png_service: TsPenugasanService) -> str:
    """Validasi penugasan ada & aktif; kembalikan `partisipan_id`-nya."""
    penugasan = png_service.get(penugasan_id)
    if not penugasan.aktif:
        raise ValidationAppError(
            f"Penugasan '{penugasan_id}' sedang tidak aktif; pencatatan log ditolak."
        )
    return penugasan.partisipan_id


@router.get(
    "/{penugasan_id}/log",
    response_model=list[TsLogRead],
    summary="Daftar log harian penugasan Time Study",
    operation_id="ts_log_list",
    dependencies=_AUTH_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND_PNG},
)
def list_log(
    penugasan_id: Annotated[str, Path(description="ID penugasan Time Study.")],
    png_service: Annotated[TsPenugasanService, Depends(get_ts_penugasan_service)],
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
) -> list[TsLogRead]:
    penugasan = png_service.get(penugasan_id)
    return log_service.list_by_partisipan(penugasan.partisipan_id)


@router.post(
    "/{penugasan_id}/log",
    response_model=TsLogRead,
    status_code=status.HTTP_201_CREATED,
    summary="Tambah log harian untuk penugasan Time Study",
    operation_id="ts_log_create",
    dependencies=_AUTH_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_NOT_FOUND_PNG,
        **_INACTIVE,
        409: {"model": ErrorResponse, "description": "Log untuk tanggal ini sudah ada."},
    },
)
def create_log(
    penugasan_id: Annotated[str, Path(description="ID penugasan Time Study.")],
    payload: TsLogCreate,
    png_service: Annotated[TsPenugasanService, Depends(get_ts_penugasan_service)],
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
) -> TsLogRead:
    partisipan_id = _require_active(penugasan_id, png_service)
    return log_service.create(partisipan_id, payload)


@router.get(
    "/{penugasan_id}/log/{log_id}",
    response_model=TsLogRead,
    summary="Ambil detail log harian Time Study",
    operation_id="ts_log_get",
    dependencies=_AUTH_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND_LOG},
)
def get_log(
    penugasan_id: Annotated[str, Path(description="ID penugasan Time Study.")],
    log_id: Annotated[str, Path(description="ID log.")],
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
) -> TsLogRead:
    return log_service.get(log_id)


@router.patch(
    "/{penugasan_id}/log/{log_id}",
    response_model=TsLogRead,
    summary="Perbarui log harian Time Study",
    operation_id="ts_log_update",
    dependencies=_AUTH_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND_LOG, **_NOT_FOUND_PNG, **_INACTIVE},
)
def update_log(
    penugasan_id: Annotated[str, Path(description="ID penugasan Time Study.")],
    log_id: Annotated[str, Path(description="ID log.")],
    payload: TsLogUpdate,
    png_service: Annotated[TsPenugasanService, Depends(get_ts_penugasan_service)],
    log_service: Annotated[TsLogService, Depends(get_ts_log_service)],
) -> TsLogRead:
    _require_active(penugasan_id, png_service)
    return log_service.update(log_id, payload)
