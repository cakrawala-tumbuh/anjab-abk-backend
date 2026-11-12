"""Endpoint cerita pra-bank dan log paparan bank tugas Task Inventory (backlog #131).

Semua rute di balik saklar `PREBANK_FREEZE` (mati -> 409 `feature_disabled`) dan memakai
`authorize_responden_access` (admin atau pemilik responden).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    READ_GUARDS,
    authorize_responden_access,
    get_current_principal,
    get_partisipan_service,
    get_ti_prabank_service,
    get_ti_responden_service,
    rate_limit,
)
from ...fitur import FiturKode, require_fitur
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...taskinv.schemas.prabank import (
    CeritaPrabankRead,
    CeritaPrabankUpsert,
    PaparanCreate,
    PaparanRead,
    PrabankRead,
)
from ...taskinv.services.prabank import TiPrabankService
from ...taskinv.services.responden import TiRespondenService

router = APIRouter()

_FITUR = Depends(require_fitur(FiturKode.PREBANK_FREEZE))
_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit), _FITUR]
_READ_GUARDS = [*READ_GUARDS, _FITUR]
_ERR = {
    401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."},
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik responden."},
    404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."},
    409: {
        "model": ErrorResponse,
        "description": "Saklar PREBANK_FREEZE mati (`feature_disabled`) atau konflik status.",
    },
    429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."},
}
_RespId = Annotated[str, Path(description="ID responden Task Inventory.")]


def _akses(
    responden_id: str,
    principal: Principal,
    rsp_service: TiRespondenService,
    par_service: PartisipanService,
) -> None:
    """Pastikan responden ada (404) dan pemanggil admin/pemiliknya (403).

    Args:
        responden_id: ID responden yang diakses.
        principal: Identitas pemanggil.
        rsp_service: Seam responden TI.
        par_service: Seam partisipan, dipakai mencocokkan pemilik.

    Raises:
        NotFoundError: Responden tidak ada.
        ForbiddenError: Pemanggil bukan admin dan bukan pemilik.
    """
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)


@router.put(
    "/responden/{responden_id}/cerita-prabank",
    response_model=CeritaPrabankRead,
    summary="Simpan cerita bebas pra-bank satu responden (ditolak bila sudah beku)",
    operation_id="taskinv_prabank_cerita_simpan",
    dependencies=_WRITE_GUARDS,
    responses={**_ERR, 422: {"model": ErrorResponse, "description": "Teks tidak valid."}},
)
def simpan_cerita(
    responden_id: _RespId,
    payload: CeritaPrabankUpsert,
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    prabank: Annotated[TiPrabankService, Depends(get_ti_prabank_service)],
) -> CeritaPrabankRead:
    """Simpan cerita; 409 `CERITA_SUDAH_DIKUNCI` bila sudah beku."""
    _akses(responden_id, principal, rsp_service, par_service)
    return prabank.simpan_cerita(responden_id, payload.teks)


@router.post(
    "/responden/{responden_id}/cerita-prabank/bekukan",
    response_model=CeritaPrabankRead,
    summary="Bekukan cerita pra-bank (idempoten; 422 CERITA_KOSONG bila belum ada teks)",
    operation_id="taskinv_prabank_cerita_bekukan",
    dependencies=_WRITE_GUARDS,
    responses={
        **_ERR,
        422: {"model": ErrorResponse, "description": "`CERITA_KOSONG`: belum ada cerita."},
    },
)
def bekukan_cerita(
    responden_id: _RespId,
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    prabank: Annotated[TiPrabankService, Depends(get_ti_prabank_service)],
) -> CeritaPrabankRead:
    """Bekukan cerita; panggilan ulang mengembalikan waktu beku yang sama."""
    _akses(responden_id, principal, rsp_service, par_service)
    return prabank.bekukan(responden_id)


@router.post(
    "/responden/{responden_id}/paparan",
    response_model=PaparanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Catat paparan bank/contoh tugas ke responden (timestamp dari server)",
    operation_id="taskinv_prabank_paparan_catat",
    dependencies=_WRITE_GUARDS,
    responses={**_ERR, 422: {"model": ErrorResponse, "description": "Body tidak valid."}},
)
def catat_paparan(
    responden_id: _RespId,
    payload: PaparanCreate,
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    prabank: Annotated[TiPrabankService, Depends(get_ti_prabank_service)],
) -> PaparanRead:
    """Catat satu paparan; status diturunkan server dari `frozen_at` cerita."""
    _akses(responden_id, principal, rsp_service, par_service)
    return prabank.catat_paparan(responden_id, payload.jenis)


@router.get(
    "/responden/{responden_id}/prabank",
    response_model=PrabankRead,
    summary="Status cerita pra-bank dan paparan satu responden",
    operation_id="taskinv_prabank_get",
    dependencies=_READ_GUARDS,
    responses=_ERR,
)
def get_prabank(
    responden_id: _RespId,
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    prabank: Annotated[TiPrabankService, Depends(get_ti_prabank_service)],
) -> PrabankRead:
    """Kembalikan cerita, `frozen_at`, `first_exposed_at`, dan `exposure_state`."""
    _akses(responden_id, principal, rsp_service, par_service)
    return prabank.baca(responden_id)
