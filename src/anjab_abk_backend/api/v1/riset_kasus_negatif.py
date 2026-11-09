"""Endpoint kasus negatif riset: khusus `tim-kajian`, append-only (tanpa sunting/hapus).

Kasus negatif dicatat per protokol `TERKUNCI` agar sintesis P08 ikut memuat kasus yang tidak
mendukung hipotesis. Pencatat (`dibuat_oleh`) selalu subjek token.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_current_principal,
    get_riset_kasus_negatif_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...schemas.common import ErrorResponse, Page
from ...schemas.riset_kasus_negatif import RisetKasusNegatifCreate, RisetKasusNegatifRead
from ...security import Principal
from ...services.riset_kasus_negatif import RisetKasusNegatifService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_PROTOKOL_404 = {404: {"model": ErrorResponse, "description": "Protokol riset tidak ditemukan."}}


@router.get(
    "/protokol/{protokol_id}/kasus-negatif",
    response_model=Page[RisetKasusNegatifRead],
    summary="Daftar kasus negatif satu protokol riset (tim-kajian)",
    operation_id="riset_kasus_negatif_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_PROTOKOL_404},
)
def list_kasus_negatif(
    protokol_id: str,
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[RisetKasusNegatifService, Depends(get_riset_kasus_negatif_service)],
) -> Page[RisetKasusNegatifRead]:
    """Daftar kasus negatif milik protokol, urut waktu pencatatan (terlama dulu)."""
    items, total = service.list_by_protokol(protokol_id, limit=page.limit, offset=page.offset)
    return Page[RisetKasusNegatifRead](
        items=items, total=total, limit=page.limit, offset=page.offset
    )


@router.post(
    "/protokol/{protokol_id}/kasus-negatif",
    response_model=RisetKasusNegatifRead,
    status_code=201,
    summary="Catat kasus negatif untuk protokol riset terkunci (tim-kajian)",
    operation_id="riset_kasus_negatif_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_PROTOKOL_404,
        409: {
            "model": ErrorResponse,
            "description": "Protokol masih DRAF (`PROTOKOL_BELUM_TERKUNCI`).",
        },
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def create_kasus_negatif(
    protokol_id: str,
    data: RisetKasusNegatifCreate,
    service: Annotated[RisetKasusNegatifService, Depends(get_riset_kasus_negatif_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> RisetKasusNegatifRead:
    """Simpan kasus negatif; pencatat (`dibuat_oleh`) selalu subjek token.

    Hanya protokol `TERKUNCI` yang boleh; tidak ada sunting maupun hapus sesudahnya.
    """

    def _aksi() -> RisetKasusNegatifRead:
        return service.create(protokol_id, data, dibuat_oleh=principal.subject)

    return run_idempotent(idem, response, RisetKasusNegatifRead, _aksi)
