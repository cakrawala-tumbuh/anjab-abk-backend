"""Endpoint resource `TsSesi`: CRUD + transisi status."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Response, status

from ...dependencies import (
    Idempotency,
    Pagination,
    get_current_principal,
    get_ts_sesi_service,
    idempotency,
    pagination_params,
    rate_limit,
)
from ...errors import ConflictError
from ...schemas.common import ErrorResponse, Page
from ...ts.schemas.sesi import TsSesiCreate, TsSesiRead, TsSesiUpdate
from ...ts.services.sesi import TsSesiService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Sesi Time Study tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}


@router.get(
    "",
    response_model=Page[TsSesiRead],
    summary="Daftar sesi Time Study",
    operation_id="ts_sesi_list",
)
def list_sesi(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[TsSesiService, Depends(get_ts_sesi_service)],
) -> Page[TsSesiRead]:
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[TsSesiRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=TsSesiRead,
    status_code=status.HTTP_201_CREATED,
    summary="Buat sesi Time Study",
    operation_id="ts_sesi_create",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
    },
)
def create_sesi(
    payload: Annotated[
        TsSesiCreate,
        Body(
            openapi_examples={
                "contoh": {
                    "summary": "Sesi Time Study Guru MTK",
                    "value": {
                        "jabatan_id": "jbt_a1b2c3d4",
                        "periode": "2025-06",
                    },
                }
            }
        ),
    ],
    service: Annotated[TsSesiService, Depends(get_ts_sesi_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> TsSesiRead:
    cached = idem.cached()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        return TsSesiRead.model_validate(cached)
    if not idem.reserve():
        raise ConflictError("Permintaan dengan Idempotency-Key ini sedang diproses.")
    try:
        item = service.create(payload)
    except Exception:
        idem.release()
        raise
    idem.remember(item)
    return item


@router.get(
    "/{sesi_id}",
    response_model=TsSesiRead,
    summary="Ambil sesi Time Study",
    operation_id="ts_sesi_get",
    responses=_NOT_FOUND,
)
def get_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi Time Study.")],
    service: Annotated[TsSesiService, Depends(get_ts_sesi_service)],
) -> TsSesiRead:
    return service.get(sesi_id)


@router.patch(
    "/{sesi_id}",
    response_model=TsSesiRead,
    summary="Perbarui sesi Time Study (hanya saat DRAFT)",
    operation_id="ts_sesi_update",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def update_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi Time Study.")],
    payload: TsSesiUpdate,
    service: Annotated[TsSesiService, Depends(get_ts_sesi_service)],
) -> TsSesiRead:
    return service.update(sesi_id, payload)


@router.delete(
    "/{sesi_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus sesi Time Study (hanya saat DRAFT)",
    operation_id="ts_sesi_delete",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def delete_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi Time Study.")],
    service: Annotated[TsSesiService, Depends(get_ts_sesi_service)],
) -> Response:
    service.delete(sesi_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{sesi_id}/buka",
    response_model=TsSesiRead,
    summary="Buka sesi Time Study (DRAFT → OPEN)",
    operation_id="ts_sesi_buka",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def buka_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi Time Study.")],
    service: Annotated[TsSesiService, Depends(get_ts_sesi_service)],
) -> TsSesiRead:
    return service.transition(sesi_id, "OPEN")


@router.post(
    "/{sesi_id}/tutup",
    response_model=TsSesiRead,
    summary="Tutup sesi Time Study (OPEN → CLOSED)",
    operation_id="ts_sesi_tutup",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def tutup_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi Time Study.")],
    service: Annotated[TsSesiService, Depends(get_ts_sesi_service)],
) -> TsSesiRead:
    return service.transition(sesi_id, "CLOSED")


@router.post(
    "/{sesi_id}/analisis",
    response_model=TsSesiRead,
    summary="Tandai sesi Time Study sebagai ANALYZED (CLOSED → ANALYZED)",
    operation_id="ts_sesi_analisis",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def analisis_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi Time Study.")],
    service: Annotated[TsSesiService, Depends(get_ts_sesi_service)],
) -> TsSesiRead:
    return service.transition(sesi_id, "ANALYZED")
