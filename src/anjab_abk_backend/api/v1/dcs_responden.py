"""Endpoint resource `DcsResponden` dan submit jawaban."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from ...dcs.schemas.jawaban import DcsJawabanBulkCreate, DcsJawabanRead
from ...dcs.schemas.responden import DcsRespondenCreate, DcsRespondenRead
from ...dcs.services.jawaban import DcsJawabanService
from ...dcs.services.responden import DcsRespondenService
from ...dcs.services.sesi import DcsSesiService
from ...dcs.services.subskala import DcsSubSkalaService
from ...dependencies import (
    get_current_principal,
    get_dcs_jawaban_service,
    get_dcs_responden_service,
    get_dcs_sesi_service,
    get_dcs_subskala_service,
    rate_limit,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi DCS tidak ditemukan."}}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}


@router.get(
    "/{sesi_id}/responden",
    response_model=list[DcsRespondenRead],
    summary="Daftar responden dalam sesi DCS",
    operation_id="dcs_responden_list",
    responses=_NOT_FOUND_SESI,
)
def list_responden(
    sesi_id: Annotated[str, Path(description="ID sesi DCS.")],
    sesi_service: Annotated[DcsSesiService, Depends(get_dcs_sesi_service)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
) -> list[DcsRespondenRead]:
    sesi_service.get(sesi_id)
    return rsp_service.list_by_sesi(sesi_id)


@router.post(
    "/{sesi_id}/responden",
    response_model=DcsRespondenRead,
    status_code=status.HTTP_201_CREATED,
    summary="Daftarkan responden ke sesi DCS",
    operation_id="dcs_responden_create",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_NOT_FOUND_SESI,
        409: {
            "model": ErrorResponse,
            "description": "Partisipan sudah terdaftar sebagai responden DCS.",
        },
    },
)
def create_responden(
    sesi_id: Annotated[str, Path(description="ID sesi DCS.")],
    payload: DcsRespondenCreate,
    sesi_service: Annotated[DcsSesiService, Depends(get_dcs_sesi_service)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
) -> DcsRespondenRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status != "OPEN":
        raise ValidationAppError(
            f"Responden hanya dapat ditambahkan saat sesi berstatus OPEN"
            f" (saat ini: {sesi.status})."
        )
    return rsp_service.create(sesi_id, payload, sesi.max_responden)


@router.get(
    "/responden/{responden_id}",
    response_model=DcsRespondenRead,
    summary="Ambil detail responden DCS",
    operation_id="dcs_responden_get",
    responses=_NOT_FOUND_RSP,
)
def get_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
) -> DcsRespondenRead:
    return rsp_service.get(responden_id)


@router.delete(
    "/responden/{responden_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus responden (hanya jika belum submit)",
    operation_id="dcs_responden_delete",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND_RSP},
)
def delete_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
) -> Response:
    rsp_service.delete(responden_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/responden/{responden_id}/jawaban",
    response_model=list[DcsJawabanRead],
    status_code=status.HTTP_201_CREATED,
    summary="Submit 42 jawaban untuk satu responden",
    operation_id="dcs_jawaban_submit",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_NOT_FOUND_RSP,
        409: {"model": ErrorResponse, "description": "Jawaban sudah ada atau item tidak valid."},
    },
)
def submit_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    payload: DcsJawabanBulkCreate,
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
    sk_service: Annotated[DcsSubSkalaService, Depends(get_dcs_subskala_service)],
) -> list[DcsJawabanRead]:
    responden = rsp_service.get(responden_id)
    if responden.sudah_submit:
        raise ValidationAppError("Responden ini sudah mengirimkan jawaban.")
    valid_item_ids = {item.item_id for item in sk_service.list_item()}
    results = jwb_service.bulk_create(responden_id, payload, valid_item_ids)
    rsp_service.mark_submitted(responden_id)
    return results


@router.get(
    "/responden/{responden_id}/jawaban",
    response_model=list[DcsJawabanRead],
    summary="Lihat jawaban responden DCS",
    operation_id="dcs_jawaban_list",
    responses=_NOT_FOUND_RSP,
)
def list_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
) -> list[DcsJawabanRead]:
    rsp_service.get(responden_id)
    return jwb_service.list_by_responden(responden_id)
