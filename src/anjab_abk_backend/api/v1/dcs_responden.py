"""Endpoint resource `DcsResponden` dan submit jawaban."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from ...core.services.partisipan import PartisipanService
from ...dcs.schemas.jawaban import DcsJawabanRead, DcsJawabanUpsert
from ...dcs.schemas.responden import DcsRespondenCreate, DcsRespondenRead
from ...dcs.services.jawaban import DcsJawabanService
from ...dcs.services.responden import DcsRespondenService
from ...dcs.services.sesi import DcsSesiService
from ...dcs.services.subskala import DcsSubSkalaService
from ...dependencies import (
    authorize_responden_access,
    get_current_principal,
    get_dcs_jawaban_service,
    get_dcs_responden_service,
    get_dcs_sesi_service,
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
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi DCS tidak ditemukan."}}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik responden."}
}


@router.get(
    "/{sesi_id}/responden",
    response_model=list[DcsRespondenRead],
    summary="Daftar responden dalam sesi DCS (admin)",
    operation_id="dcs_responden_list",
    dependencies=[Depends(require_admin)],
    responses={**_AUTH, **_FORBIDDEN, **_NOT_FOUND_SESI},
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
    summary="Daftarkan responden ke sesi DCS (admin)",
    operation_id="dcs_responden_create",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
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
    "/responden/{responden_id}",
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
    "/responden/{responden_id}/jawaban",
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
        422: {"model": ErrorResponse, "description": "Responden sudah submit final."},
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
    "/responden/{responden_id}/jawaban/submit",
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
            "description": "Responden sudah submit, atau jawaban tersimpan belum lengkap.",
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
    "/responden/{responden_id}/jawaban",
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
