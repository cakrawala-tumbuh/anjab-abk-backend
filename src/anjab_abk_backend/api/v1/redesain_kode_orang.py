"""Endpoint kode orang (pseudonim) redesain: peta khusus `tim-kajian` + `/saya`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    READ_GUARDS,
    Pagination,
    get_kode_orang_pemanggil,
    get_kode_orang_service,
    get_partisipan_service,
    pagination_params,
    rate_limit,
    require_tim_kajian,
    require_tim_kajian_atau_pengisi,
)
from ...errors import ForbiddenError
from ...redesain.schemas.kode_orang import (
    KodeOrangCreate,
    KodeOrangRead,
    KodeOrangSaya,
    KodeOrangUpdate,
)
from ...redesain.services.kode_orang import KodeOrangService
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ...security import Principal

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Kode orang tidak ditemukan."}}


@router.get(
    "/saya",
    response_model=KodeOrangSaya,
    summary="Kode orang milik pemanggil (tim-kajian / sekolah-pengisi)",
    operation_id="redesain_kode_orang_saya",
    dependencies=[*READ_GUARDS, Depends(require_tim_kajian_atau_pengisi)],
    responses={
        **_AUTH,
        **_RATE,
        403: {"model": ErrorResponse, "description": "Bukan tim-kajian/sekolah-pengisi."},
    },
)
def kode_saya(
    principal: Annotated[Principal, Depends(require_tim_kajian_atau_pengisi)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
) -> KodeOrangSaya:
    """Kembalikan kode pseudonim pemanggil (dibuat bila belum ada); tanpa `partisipan_id`."""
    par = par_service.get_by_subject(principal.subject)
    if par is None:
        raise ForbiddenError("Akses ditolak: pemanggil tidak terdaftar sebagai partisipan.")
    return KodeOrangSaya(kode=service.untuk_partisipan(par.id).kode)


@router.get(
    "",
    response_model=Page[KodeOrangRead],
    summary="Daftar kode orang (tim-kajian)",
    operation_id="redesain_kode_orang_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_kode_orang(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
) -> Page[KodeOrangRead]:
    """Daftar peta kode orang."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[KodeOrangRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=KodeOrangRead,
    status_code=201,
    summary="Daftarkan orang/narasumber baru (tim-kajian)",
    operation_id="redesain_kode_orang_create",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "partisipan_id tidak ditemukan."},
        409: {"model": ErrorResponse, "description": "Partisipan sudah memiliki kode."},
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def create_kode_orang(
    data: KodeOrangCreate,
    service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> KodeOrangRead:
    """Buat kode baru; `kode` dibangkitkan sistem dari sequence."""
    return service.create(data, pelaku_kode_orang=pelaku)


@router.post(
    "/search",
    response_model=Page[KodeOrangRead],
    summary="Cari kode orang (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_kode_orang_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_kode_orang(
    req: SearchRequest,
    service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
) -> Page[KodeOrangRead]:
    """Cari dengan domain ala Odoo; field di-whitelist, nilai bound parameter."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[KodeOrangRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{kode_orang_id}",
    response_model=KodeOrangRead,
    summary="Detail kode orang (tim-kajian)",
    operation_id="redesain_kode_orang_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_kode_orang(
    kode_orang_id: str,
    service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
) -> KodeOrangRead:
    """Ambil satu baris kode orang."""
    return service.get(kode_orang_id)


@router.patch(
    "/{kode_orang_id}",
    response_model=KodeOrangRead,
    summary="Ubah keterangan peran kode orang (tim-kajian)",
    operation_id="redesain_kode_orang_update",
    dependencies=_WRITE,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def update_kode_orang(
    kode_orang_id: str,
    data: KodeOrangUpdate,
    service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> KodeOrangRead:
    """Ubah `keterangan_peran`; `kode` dan `partisipan_id` tidak dapat diubah."""
    return service.update(kode_orang_id, data, pelaku_kode_orang=pelaku)
