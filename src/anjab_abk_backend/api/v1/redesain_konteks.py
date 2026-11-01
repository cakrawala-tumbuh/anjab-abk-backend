"""Endpoint katalog konteks redesain: khusus `tim-kajian`, tanpa DELETE."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...dependencies import (
    READ_GUARDS,
    Pagination,
    get_kode_orang_pemanggil,
    get_konteks_service,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...redesain.schemas.konteks import KonteksCreate, KonteksRead, KonteksUpdate
from ...redesain.services.konteks import KonteksService
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Konteks tidak ditemukan."}}


@router.get(
    "",
    response_model=Page[KonteksRead],
    summary="Daftar konteks redesain (tim-kajian)",
    operation_id="redesain_konteks_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_konteks(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[KonteksService, Depends(get_konteks_service)],
) -> Page[KonteksRead]:
    """Daftar konteks berurutan menurut kode."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[KonteksRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=KonteksRead,
    status_code=201,
    summary="Tambah konteks redesain (tim-kajian)",
    operation_id="redesain_konteks_create",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {"model": ErrorResponse, "description": "Kode konteks sudah ada."},
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def create_konteks(
    data: KonteksCreate,
    service: Annotated[KonteksService, Depends(get_konteks_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> KonteksRead:
    """Buat konteks baru dan catat riwayatnya."""
    return service.create(data, pelaku_kode_orang=pelaku)


@router.post(
    "/search",
    response_model=Page[KonteksRead],
    summary="Cari konteks (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_konteks_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_konteks(
    req: SearchRequest,
    service: Annotated[KonteksService, Depends(get_konteks_service)],
) -> Page[KonteksRead]:
    """Cari dengan domain ala Odoo; field di-whitelist, nilai bound parameter."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[KonteksRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{konteks_id}",
    response_model=KonteksRead,
    summary="Detail konteks redesain (tim-kajian)",
    operation_id="redesain_konteks_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_konteks(
    konteks_id: str,
    service: Annotated[KonteksService, Depends(get_konteks_service)],
) -> KonteksRead:
    """Ambil satu konteks."""
    return service.get(konteks_id)


@router.patch(
    "/{konteks_id}",
    response_model=KonteksRead,
    summary="Ubah konteks redesain (tim-kajian)",
    operation_id="redesain_konteks_update",
    dependencies=_WRITE,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def update_konteks(
    konteks_id: str,
    data: KonteksUpdate,
    service: Annotated[KonteksService, Depends(get_konteks_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> KonteksRead:
    """Ubah parsial konteks (termasuk `aktif=false` untuk menonaktifkan); `kode` tetap."""
    return service.update(konteks_id, data, pelaku_kode_orang=pelaku)
