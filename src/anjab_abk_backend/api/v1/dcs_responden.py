"""Endpoint resource `DcsResponden` (penugasan langsung) dan jawaban."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from ...core.services.partisipan import PartisipanService
from ...dcs.schemas.jawaban import DcsJawabanRead, DcsJawabanUpsert
from ...dcs.schemas.responden import DcsRespondenCreate, DcsRespondenRead
from ...dcs.services.jawaban import DcsJawabanService
from ...dcs.services.responden import DcsRespondenService
from ...dcs.services.subskala import DcsSubSkalaService
from ...dependencies import (
    authorize_responden_access,
    get_current_principal,
    get_dcs_jawaban_service,
    get_dcs_responden_service,
    get_dcs_subskala_service,
    get_partisipan_service,
    rate_limit,
    require_admin,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse
from ...security import Principal

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik responden."}
}


@router.get(
    "",
    response_model=list[DcsRespondenRead],
    summary="Daftar seluruh responden DCS (admin)",
    operation_id="dcs_responden_list",
    dependencies=[Depends(require_admin)],
    responses={**_AUTH, **_FORBIDDEN},
)
def list_responden(
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
) -> list[DcsRespondenRead]:
    return rsp_service.list_all()


@router.post(
    "",
    response_model=list[DcsRespondenRead],
    status_code=status.HTTP_201_CREATED,
    summary="Tugaskan (assign) responden DCS — bulk (admin)",
    operation_id="dcs_responden_create",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {
            "model": ErrorResponse,
            "description": (
                "Instrumen DCS tidak OPEN, atau salah satu partisipan sudah terdaftar"
                " sebagai responden DCS."
            ),
        },
    },
)
def create_responden(
    payload: DcsRespondenCreate,
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
) -> list[DcsRespondenRead]:
    return rsp_service.create_banyak(payload.partisipan_ids)


@router.get(
    "/{responden_id}",
    response_model=DcsRespondenRead,
    summary="Ambil detail responden DCS (admin atau pemilik)",
    operation_id="dcs_responden_get",
    responses={**_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def get_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> DcsRespondenRead:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    return responden


@router.delete(
    "/{responden_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus responden (admin; hanya jika belum submit)",
    operation_id="dcs_responden_delete",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def delete_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
) -> Response:
    rsp_service.delete(responden_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{responden_id}/jawaban",
    response_model=list[DcsJawabanRead],
    summary="Simpan draft jawaban (parsial) untuk satu responden",
    operation_id="dcs_jawaban_save_draft",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_RSP,
        409: {"model": ErrorResponse, "description": "Item tidak dikenal."},
        422: {
            "model": ErrorResponse,
            "description": "Responden sudah submit final, atau instrumen tidak OPEN.",
        },
    },
)
def save_draft_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    payload: DcsJawabanUpsert,
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
    sk_service: Annotated[DcsSubSkalaService, Depends(get_dcs_subskala_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> list[DcsJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    if responden.sudah_submit:
        raise ValidationAppError(
            "Responden ini sudah mengirimkan jawaban; draft tidak bisa diubah."
        )
    valid_item_ids = {item.item_id for item in sk_service.list_item()}
    return jwb_service.upsert(responden_id, payload, valid_item_ids)


@router.post(
    "/{responden_id}/jawaban/submit",
    response_model=list[DcsJawabanRead],
    status_code=status.HTTP_201_CREATED,
    summary="Finalisasi (submit) 42 jawaban tersimpan untuk satu responden",
    operation_id="dcs_jawaban_submit",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_RSP,
        422: {
            "model": ErrorResponse,
            "description": (
                "Responden sudah submit, jawaban tersimpan belum lengkap, atau instrumen"
                " tidak OPEN."
            ),
        },
    },
)
def submit_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
    sk_service: Annotated[DcsSubSkalaService, Depends(get_dcs_subskala_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> list[DcsJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    if responden.sudah_submit:
        raise ValidationAppError("Responden ini sudah mengirimkan jawaban.")
    valid_item_ids = {item.item_id for item in sk_service.list_item()}
    results = jwb_service.submit(responden_id, valid_item_ids)
    rsp_service.mark_submitted(responden_id)
    return results


@router.get(
    "/{responden_id}/jawaban",
    response_model=list[DcsJawabanRead],
    summary="Lihat jawaban responden DCS (admin atau pemilik)",
    operation_id="dcs_jawaban_list",
    responses={**_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def list_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> list[DcsJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    return jwb_service.list_by_responden(responden_id)
