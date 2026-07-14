"""Endpoint resource `OpmResponden` dan submit jawaban."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    READ_GUARDS,
    authorize_responden_access,
    get_current_principal,
    get_opm_jawaban_service,
    get_opm_responden_service,
    get_opm_sesi_service,
    get_partisipan_service,
    rate_limit,
    require_admin,
)
from ...errors import ValidationAppError
from ...opm.schemas.jawaban import OpmJawabanRead, OpmJawabanUpsert
from ...opm.schemas.responden import OpmRespondenBulkCreate, OpmRespondenCreate, OpmRespondenRead
from ...opm.services.jawaban import OpmJawabanService
from ...opm.services.responden import OpmRespondenService
from ...opm.services.sesi import OpmSesiService
from ...schemas.common import BulkAssignResult, ErrorResponse
from ...security import Principal

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi OPM tidak ditemukan."}}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik responden."}
}


@router.get(
    "/{sesi_id}/responden",
    response_model=list[OpmRespondenRead],
    summary="Daftar responden dalam sesi OPM (admin)",
    operation_id="opm_responden_list",
    dependencies=[Depends(require_admin)],
    responses={**_AUTH, **_FORBIDDEN, **_NOT_FOUND_SESI},
)
def list_responden(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    sesi_service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
) -> list[OpmRespondenRead]:
    sesi_service.get(sesi_id)
    return rsp_service.list_by_sesi(sesi_id)


@router.post(
    "/{sesi_id}/responden",
    response_model=OpmRespondenRead,
    status_code=status.HTTP_201_CREATED,
    summary="Daftarkan responden manual ke sesi OPM (admin; wajib anggota SME panel jabatan sesi)",
    operation_id="opm_responden_create",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_SESI,
        409: {
            "model": ErrorResponse,
            "description": "Partisipan sudah terdaftar sebagai responden OPM di sesi ini.",
        },
        422: {
            "model": ErrorResponse,
            "description": "Sesi bukan DRAFT/OPEN, atau partisipan bukan anggota SME panel.",
        },
    },
)
def create_responden(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    payload: OpmRespondenCreate,
    sesi_service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
) -> OpmRespondenRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status not in ("DRAFT", "OPEN"):
        raise ValidationAppError(
            f"Responden hanya dapat ditambahkan saat sesi DRAFT/OPEN (saat ini: {sesi.status})."
        )
    return rsp_service.create(sesi_id, payload, sesi.max_responden, sesi.jabatan_id)


@router.post(
    "/{sesi_id}/responden/bulk",
    response_model=BulkAssignResult[OpmRespondenRead],
    status_code=status.HTTP_201_CREATED,
    summary="Tugaskan banyak partisipan sekaligus sebagai responden OPM (admin, idempoten)",
    operation_id="opm_responden_create_banyak",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_SESI,
        422: {
            "model": ErrorResponse,
            "description": "Sesi bukan DRAFT/OPEN.",
        },
    },
)
def create_responden_banyak(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    payload: OpmRespondenBulkCreate,
    sesi_service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
) -> BulkAssignResult[OpmRespondenRead]:
    sesi = sesi_service.get(sesi_id)
    if sesi.status not in ("DRAFT", "OPEN"):
        raise ValidationAppError(
            f"Responden hanya dapat ditambahkan saat sesi DRAFT/OPEN (saat ini: {sesi.status})."
        )
    return rsp_service.assign_banyak(
        sesi_id,
        payload.partisipan_ids,
        max_responden=sesi.max_responden,
        jabatan_id=sesi.jabatan_id,
    )


@router.get(
    "/responden/{responden_id}",
    response_model=OpmRespondenRead,
    summary="Ambil detail responden OPM (admin atau pemilik)",
    operation_id="opm_responden_get",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def get_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> OpmRespondenRead:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    return responden


@router.delete(
    "/responden/{responden_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus responden (admin; hanya jika belum submit)",
    operation_id="opm_responden_delete",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def delete_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
) -> Response:
    rsp_service.delete(responden_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/responden/{responden_id}/jawaban",
    response_model=list[OpmJawabanRead],
    summary="Simpan draft rating (Importance/Frequency/Criticality) untuk satu responden",
    operation_id="opm_jawaban_save_draft",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_RSP,
        422: {
            "model": ErrorResponse,
            "description": "Sesi bukan OPEN, responden sudah submit, atau kode task tidak dikenal.",
        },
    },
)
def save_draft_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    payload: OpmJawabanUpsert,
    principal: Annotated[Principal, Depends(get_current_principal)],
    sesi_service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    jwb_service: Annotated[OpmJawabanService, Depends(get_opm_jawaban_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> list[OpmJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    sesi = sesi_service.get(responden.sesi_id)
    if sesi.status != "OPEN":
        raise ValidationAppError(
            f"Jawaban hanya dapat disimpan saat sesi berstatus OPEN (saat ini: {sesi.status})."
        )
    if responden.sudah_submit:
        raise ValidationAppError(
            "Responden ini sudah mengirimkan jawaban; draft tidak bisa diubah."
        )
    valid_task_kodes = sesi_service.get_task_kodes(responden.sesi_id)
    return jwb_service.upsert(responden_id, payload, valid_task_kodes)


@router.post(
    "/responden/{responden_id}/jawaban/submit",
    response_model=list[OpmJawabanRead],
    status_code=status.HTTP_201_CREATED,
    summary="Finalisasi (submit) rating tersimpan untuk satu responden",
    operation_id="opm_jawaban_submit",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_RSP,
        422: {
            "model": ErrorResponse,
            "description": "Sesi bukan OPEN, responden sudah submit, atau set task tidak lengkap.",
        },
    },
)
def submit_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    sesi_service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    jwb_service: Annotated[OpmJawabanService, Depends(get_opm_jawaban_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> list[OpmJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    sesi = sesi_service.get(responden.sesi_id)
    if sesi.status != "OPEN":
        raise ValidationAppError(
            f"Jawaban hanya dapat disubmit saat sesi berstatus OPEN (saat ini: {sesi.status})."
        )
    if responden.sudah_submit:
        raise ValidationAppError("Responden ini sudah mengirimkan jawaban.")
    valid_task_kodes = sesi_service.get_task_kodes(responden.sesi_id)
    results = jwb_service.submit(responden_id, valid_task_kodes)
    rsp_service.mark_submitted(responden_id)
    return results


@router.get(
    "/responden/{responden_id}/jawaban",
    response_model=list[OpmJawabanRead],
    summary="Lihat jawaban responden (admin atau pemilik)",
    operation_id="opm_jawaban_list",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def list_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    jwb_service: Annotated[OpmJawabanService, Depends(get_opm_jawaban_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> list[OpmJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    return jwb_service.list_by_responden(responden_id)
