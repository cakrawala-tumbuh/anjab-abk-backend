"""Endpoint bukti redesain: khusus `tim-kajian`, tanpa DELETE."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_bukti_service,
    get_kode_orang_pemanggil,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...etag import check_if_match, compute_etag
from ...redesain.schemas.bukti import BuktiCreate, BuktiRead, BuktiUpdate
from ...redesain.services.bukti import BuktiService
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
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Bukti tidak ditemukan."}}


@router.get(
    "",
    response_model=Page[BuktiRead],
    summary="Daftar bukti redesain (tim-kajian)",
    operation_id="redesain_bukti_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_bukti(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[BuktiService, Depends(get_bukti_service)],
) -> Page[BuktiRead]:
    """Daftar bukti berurutan menurut kode."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[BuktiRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=BuktiRead,
    status_code=201,
    summary="Tambah bukti redesain (tim-kajian)",
    operation_id="redesain_bukti_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {"model": ErrorResponse, "description": "Kode bukti bentrok."},
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def create_bukti(
    data: BuktiCreate,
    service: Annotated[BuktiService, Depends(get_bukti_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> BuktiRead:
    """Buat bukti baru (kode `B-NNNN`); 422 bila masalah, langkah, atau kode orang tak valid."""

    def _aksi() -> BuktiRead:
        return service.create(data, pelaku_kode_orang=pelaku)

    return run_idempotent(idem, response, BuktiRead, _aksi)


@router.post(
    "/search",
    response_model=Page[BuktiRead],
    summary="Cari bukti (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_bukti_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_bukti(
    req: SearchRequest,
    service: Annotated[BuktiService, Depends(get_bukti_service)],
) -> Page[BuktiRead]:
    """Cari dengan domain ala Odoo; field di-whitelist, nilai bound parameter."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[BuktiRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{bukti_id}",
    response_model=BuktiRead,
    summary="Detail bukti redesain (tim-kajian)",
    operation_id="redesain_bukti_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_bukti(
    bukti_id: str,
    service: Annotated[BuktiService, Depends(get_bukti_service)],
    response: Response,
) -> BuktiRead:
    """Ambil satu bukti."""
    item = service.get(bukti_id)
    response.headers["ETag"] = compute_etag(item)
    return item


@router.patch(
    "/{bukti_id}",
    response_model=BuktiRead,
    summary="Ubah bukti redesain (tim-kajian)",
    operation_id="redesain_bukti_update",
    dependencies=_WRITE,
    responses={**PRECONDITION_RESPONSES, **_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def update_bukti(
    bukti_id: str,
    data: BuktiUpdate,
    service: Annotated[BuktiService, Depends(get_bukti_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: IfMatchHeader = None,
) -> BuktiRead:
    """Ubah parsial bukti (mis. status pemeriksaan); `kode` dan `masalah_id` tetap."""
    check_if_match(service.get(bukti_id), if_match, settings.require_if_match)
    item = service.update(bukti_id, data, pelaku_kode_orang=pelaku)
    response.headers["ETag"] = compute_etag(item)
    return item
