"""Endpoint catatan versi metode redesain: khusus `tim-kajian`, tanpa DELETE."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_kode_orang_pemanggil,
    get_versi_metode_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...etag import check_if_match, compute_etag
from ...redesain.schemas.versi_metode import VersiMetodeCreate, VersiMetodeRead, VersiMetodeUpdate
from ...redesain.services.versi_metode import VersiMetodeService
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ..concurrency import (
    IDEMPOTENCY_RESPONSES,
    PRECONDITION_RESPONSES,
    IfMatchHeader,
    run_idempotent,
)

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Catatan versi metode tidak ditemukan."}}


@router.get(
    "",
    response_model=Page[VersiMetodeRead],
    summary="Daftar catatan versi metode (tim-kajian)",
    operation_id="redesain_versi_metode_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_versi_metode(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[VersiMetodeService, Depends(get_versi_metode_service)],
) -> Page[VersiMetodeRead]:
    """Daftar catatan berurutan menurut tanggal, versi, bagian."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[VersiMetodeRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=VersiMetodeRead,
    status_code=201,
    summary="Tambah catatan versi metode (tim-kajian)",
    operation_id="redesain_versi_metode_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {"model": ErrorResponse, "description": "Pasangan versi dan bagian sudah ada."},
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def create_versi_metode(
    data: VersiMetodeCreate,
    service: Annotated[VersiMetodeService, Depends(get_versi_metode_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> VersiMetodeRead:
    """Buat catatan baru; 409 bila pasangan versi+bagian sudah ada."""

    def _aksi() -> VersiMetodeRead:
        return service.create(data, pelaku_kode_orang=pelaku)

    return run_idempotent(idem, response, VersiMetodeRead, _aksi)


@router.post(
    "/search",
    response_model=Page[VersiMetodeRead],
    summary="Cari catatan versi (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_versi_metode_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_versi_metode(
    req: SearchRequest,
    service: Annotated[VersiMetodeService, Depends(get_versi_metode_service)],
) -> Page[VersiMetodeRead]:
    """Cari dengan domain ala Odoo; field di-whitelist, nilai bound parameter."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[VersiMetodeRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{versi_id}",
    response_model=VersiMetodeRead,
    summary="Detail catatan versi metode (tim-kajian)",
    operation_id="redesain_versi_metode_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_versi_metode(
    versi_id: str,
    service: Annotated[VersiMetodeService, Depends(get_versi_metode_service)],
    response: Response,
) -> VersiMetodeRead:
    """Ambil satu catatan."""
    item = service.get(versi_id)
    response.headers["ETag"] = compute_etag(item)
    return item


@router.patch(
    "/{versi_id}",
    response_model=VersiMetodeRead,
    summary="Ubah catatan versi metode (tim-kajian)",
    operation_id="redesain_versi_metode_update",
    dependencies=_WRITE,
    responses={
        **PRECONDITION_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        409: {"model": ErrorResponse, "description": "Pasangan versi dan bagian sudah ada."},
    },
)
def update_versi_metode(
    versi_id: str,
    data: VersiMetodeUpdate,
    service: Annotated[VersiMetodeService, Depends(get_versi_metode_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: IfMatchHeader = None,
) -> VersiMetodeRead:
    """Ubah parsial catatan; 409 bila pasangan versi+bagian jadi bentrok."""
    check_if_match(service.get(versi_id), if_match, settings.require_if_match)
    item = service.update(versi_id, data, pelaku_kode_orang=pelaku)
    response.headers["ETag"] = compute_etag(item)
    return item
