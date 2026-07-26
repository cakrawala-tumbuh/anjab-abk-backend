"""Endpoint usulan uraian tugas tambahan dari partisipan Tahap 1 (backlog `#26`).

Responden Tahap 1 mencatat usulan uraian tugas baru di bawah tugas pokok (dan opsional
detil tugas) pilihannya, saat tugas yang ia kerjakan tidak ada di katalog. Review &
materialisasi usulan ke katalog di Tahap 2 adalah item lanjutan terpisah (`#27`).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response, status

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    READ_GUARDS,
    authorize_responden_access,
    get_current_principal,
    get_detil_tugas_service,
    get_partisipan_service,
    get_ti_responden_service,
    get_ti_sesi_service,
    get_ti_usulan_service,
    get_tugas_pokok_service,
    rate_limit,
)
from ...errors import NotFoundError, ValidationAppError
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...taskinv.schemas.usulan import TiUsulanCreate, TiUsulanRead
from ...taskinv.services.detil_tugas import DetilTugasService
from ...taskinv.services.responden import TiRespondenService
from ...taskinv.services.sesi import TiSesiService
from ...taskinv.services.tugas_pokok import TugasPokokService
from ...taskinv.services.usulan import TiUsulanService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik responden."}
}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_NOT_FOUND_USULAN = {404: {"model": ErrorResponse, "description": "Usulan tidak ditemukan."}}
_VALIDASI_USULAN = {
    "model": ErrorResponse,
    "description": (
        "Sesi bukan TAHAP1, responden sudah submit Tahap 1, tugas_pokok_id tidak"
        " terkait jabatan sesi, atau detil_tugas_id bukan turunan tugas_pokok_id."
    ),
}


def _validasi_induk_usulan(
    payload: TiUsulanCreate,
    jabatan_id: str,
    tp_service: TugasPokokService,
    dt_service: DetilTugasService,
) -> None:
    """Pastikan `tugas_pokok_id`/`detil_tugas_id` payload valid untuk jabatan sesi.

    Args:
        payload: payload usulan yang sedang divalidasi.
        jabatan_id: `jabatan_id` sesi tempat usulan dicatat.
        tp_service: seam `TugasPokokService` untuk resolusi tugas pokok.
        dt_service: seam `DetilTugasService` untuk resolusi detil tugas.

    Raises:
        ValidationAppError: `tugas_pokok_id` tidak ditemukan/tidak terkait
            `jabatan_id`, atau `detil_tugas_id` tidak ditemukan/bukan turunan
            `tugas_pokok_id`.
    """
    try:
        tp = tp_service.get(payload.tugas_pokok_id)
    except NotFoundError:
        raise ValidationAppError(
            f"TugasPokok '{payload.tugas_pokok_id}' tidak ditemukan."
        ) from None
    if jabatan_id not in tp.jabatan_ids:
        raise ValidationAppError(
            f"TugasPokok '{payload.tugas_pokok_id}' tidak terkait dengan jabatan sesi ini."
        )
    if payload.detil_tugas_id is not None:
        try:
            dt = dt_service.get(payload.detil_tugas_id)
        except NotFoundError:
            raise ValidationAppError(
                f"DetilTugas '{payload.detil_tugas_id}' tidak ditemukan."
            ) from None
        if dt.tugas_pokok_id != payload.tugas_pokok_id:
            raise ValidationAppError(
                f"DetilTugas '{payload.detil_tugas_id}' bukan turunan"
                f" TugasPokok '{payload.tugas_pokok_id}'."
            )


@router.post(
    "/sesi/responden/{responden_id}/usulan",
    response_model=TiUsulanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Catat usulan uraian tugas baru dari responden Tahap 1",
    operation_id="taskinv_usulan_create",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_RSP,
        422: _VALIDASI_USULAN,
    },
)
def create_usulan(
    responden_id: Annotated[str, Path(description="ID responden.")],
    payload: TiUsulanCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    usulan_service: Annotated[TiUsulanService, Depends(get_ti_usulan_service)],
    tp_service: Annotated[TugasPokokService, Depends(get_tugas_pokok_service)],
    dt_service: Annotated[DetilTugasService, Depends(get_detil_tugas_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> TiUsulanRead:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    sesi = sesi_service.get(responden.sesi_id)
    if sesi.status != "TAHAP1":
        raise ValidationAppError(
            f"Usulan hanya dapat dicatat saat sesi berstatus TAHAP1 (saat ini: {sesi.status})."
        )
    if responden.tahap1_submit:
        raise ValidationAppError(
            "Responden ini sudah menyelesaikan Tahap 1; usulan tidak bisa dicatat."
        )
    _validasi_induk_usulan(payload, sesi.jabatan_id, tp_service, dt_service)
    return usulan_service.create(responden_id, sesi.id, payload)


@router.get(
    "/sesi/responden/{responden_id}/usulan",
    response_model=list[TiUsulanRead],
    summary="Daftar usulan uraian tugas milik satu responden (admin atau pemilik)",
    operation_id="taskinv_usulan_list",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def list_usulan(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    usulan_service: Annotated[TiUsulanService, Depends(get_ti_usulan_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> list[TiUsulanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    return usulan_service.list_by_responden(responden_id)


@router.delete(
    "/usulan/{usulan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus usulan uraian tugas milik sendiri (admin atau pemilik, sebelum submit)",
    operation_id="taskinv_usulan_delete",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_USULAN,
        422: _VALIDASI_USULAN,
    },
)
def delete_usulan(
    usulan_id: Annotated[str, Path(description="ID usulan.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    usulan_service: Annotated[TiUsulanService, Depends(get_ti_usulan_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> Response:
    usulan = usulan_service.get(usulan_id)
    responden = rsp_service.get(usulan.responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    sesi = sesi_service.get(usulan.sesi_id)
    if sesi.status != "TAHAP1":
        raise ValidationAppError(
            f"Usulan hanya dapat dihapus saat sesi berstatus TAHAP1 (saat ini: {sesi.status})."
        )
    if responden.tahap1_submit:
        raise ValidationAppError(
            "Responden ini sudah menyelesaikan Tahap 1; usulan tidak bisa dihapus."
        )
    usulan_service.delete(usulan_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
