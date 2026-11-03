"""Endpoint katalog konteks redesain: khusus `tim-kajian`, tanpa DELETE."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_kode_orang_pemanggil,
    get_konteks_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...etag import check_if_match, compute_etag
from ...redesain.schemas.konteks import KonteksCreate, KonteksRead, KonteksUpdate
from ...redesain.services.konteks import KonteksService
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
        **IDEMPOTENCY_RESPONSES,
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
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> KonteksRead:
    """Buat konteks baru dan catat riwayatnya."""

    def _aksi() -> KonteksRead:
        return service.create(data, pelaku_kode_orang=pelaku)

    return run_idempotent(idem, response, KonteksRead, _aksi)


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
    response: Response,
) -> KonteksRead:
    """Ambil satu konteks."""
    item = service.get(konteks_id)
    response.headers["ETag"] = compute_etag(item)
    return item


@router.patch(
    "/{konteks_id}",
    response_model=KonteksRead,
    summary="Ubah konteks redesain (tim-kajian)",
    operation_id="redesain_konteks_update",
    dependencies=_WRITE,
    responses={**PRECONDITION_RESPONSES, **_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def update_konteks(
    konteks_id: str,
    data: KonteksUpdate,
    service: Annotated[KonteksService, Depends(get_konteks_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: IfMatchHeader = None,
) -> KonteksRead:
    """Ubah parsial konteks (termasuk `aktif=false` untuk menonaktifkan); `kode` tetap."""
    check_if_match(service.get(konteks_id), if_match, settings.require_if_match)
    item = service.update(konteks_id, data, pelaku_kode_orang=pelaku)
    response.headers["ETag"] = compute_etag(item)
    return item
