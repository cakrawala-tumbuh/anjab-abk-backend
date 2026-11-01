"""Endpoint penilaian redesain + saran triase otomatis: khusus `tim-kajian`, tanpa DELETE."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...dependencies import (
    READ_GUARDS,
    Pagination,
    get_kode_orang_pemanggil,
    get_penilaian_service,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...redesain.schemas.penilaian import PenilaianCreate, PenilaianRead, PenilaianUpdate
from ...redesain.services.penilaian import PenilaianService
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Penilaian tidak ditemukan."}}


@router.get(
    "",
    response_model=Page[PenilaianRead],
    summary="Daftar penilaian redesain (tim-kajian)",
    operation_id="redesain_penilaian_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_penilaian(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[PenilaianService, Depends(get_penilaian_service)],
) -> Page[PenilaianRead]:
    """Daftar penilaian berurutan menurut waktu dibuat."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[PenilaianRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=PenilaianRead,
    status_code=201,
    summary="Tambah penilaian redesain (tim-kajian)",
    operation_id="redesain_penilaian_create",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {"model": ErrorResponse, "description": "Masalah sudah punya penilaian."},
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def create_penilaian(
    data: PenilaianCreate,
    service: Annotated[PenilaianService, Depends(get_penilaian_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> PenilaianRead:
    """Buat penilaian satu masalah; `saran_otomatis` dihitung sistem, 409 bila sudah ada."""
    return service.create(data, pelaku_kode_orang=pelaku)


@router.post(
    "/search",
    response_model=Page[PenilaianRead],
    summary="Cari penilaian (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_penilaian_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_penilaian(
    req: SearchRequest,
    service: Annotated[PenilaianService, Depends(get_penilaian_service)],
) -> Page[PenilaianRead]:
    """Cari dengan domain ala Odoo; field di-whitelist, nilai bound parameter."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[PenilaianRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{penilaian_id}",
    response_model=PenilaianRead,
    summary="Detail penilaian redesain (tim-kajian)",
    operation_id="redesain_penilaian_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_penilaian(
    penilaian_id: str,
    service: Annotated[PenilaianService, Depends(get_penilaian_service)],
) -> PenilaianRead:
    """Ambil satu penilaian."""
    return service.get(penilaian_id)


@router.patch(
    "/{penilaian_id}",
    response_model=PenilaianRead,
    summary="Ubah penilaian redesain (tim-kajian)",
    operation_id="redesain_penilaian_update",
    dependencies=_WRITE,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def update_penilaian(
    penilaian_id: str,
    data: PenilaianUpdate,
    service: Annotated[PenilaianService, Depends(get_penilaian_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> PenilaianRead:
    """Ubah parsial penilaian; `saran_otomatis` dihitung ulang, `masalah_id` tetap."""
    return service.update(penilaian_id, data, pelaku_kode_orang=pelaku)
