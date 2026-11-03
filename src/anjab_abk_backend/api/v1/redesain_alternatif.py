"""Endpoint alternatif redesain: khusus `tim-kajian`, tanpa DELETE."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_alternatif_service,
    get_kode_orang_pemanggil,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...etag import check_if_match, compute_etag
from ...redesain.schemas.alternatif import AlternatifCreate, AlternatifRead, AlternatifUpdate
from ...redesain.services.alternatif import AlternatifService
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
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Alternatif tidak ditemukan."}}


@router.get(
    "",
    response_model=Page[AlternatifRead],
    summary="Daftar alternatif redesain (tim-kajian)",
    operation_id="redesain_alternatif_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_alternatif(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
) -> Page[AlternatifRead]:
    """Daftar alternatif berurutan menurut kode."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[AlternatifRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=AlternatifRead,
    status_code=201,
    summary="Tambah alternatif redesain (tim-kajian)",
    operation_id="redesain_alternatif_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {"model": ErrorResponse, "description": "Kode alternatif bentrok."},
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def create_alternatif(
    data: AlternatifCreate,
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> AlternatifRead:
    """Buat alternatif baru (kode `U-NNN`); 422 bila rujukan atau aturan opsi/status tak valid."""

    def _aksi() -> AlternatifRead:
        return service.create(data, pelaku_kode_orang=pelaku)

    return run_idempotent(idem, response, AlternatifRead, _aksi)


@router.post(
    "/search",
    response_model=Page[AlternatifRead],
    summary="Cari alternatif (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_alternatif_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_alternatif(
    req: SearchRequest,
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
) -> Page[AlternatifRead]:
    """Cari dengan domain ala Odoo; field di-whitelist, nilai bound parameter."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[AlternatifRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{alternatif_id}",
    response_model=AlternatifRead,
    summary="Detail alternatif redesain (tim-kajian)",
    operation_id="redesain_alternatif_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_alternatif(
    alternatif_id: str,
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
    response: Response,
) -> AlternatifRead:
    """Ambil satu alternatif."""
    item = service.get(alternatif_id)
    response.headers["ETag"] = compute_etag(item)
    return item


@router.patch(
    "/{alternatif_id}",
    response_model=AlternatifRead,
    summary="Ubah alternatif redesain (tim-kajian)",
    operation_id="redesain_alternatif_update",
    dependencies=_WRITE,
    responses={**PRECONDITION_RESPONSES, **_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def update_alternatif(
    alternatif_id: str,
    data: AlternatifUpdate,
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: IfMatchHeader = None,
) -> AlternatifRead:
    """Ubah parsial alternatif (mis. status telaah); `kode` dan `masalah_id` tetap."""
    check_if_match(service.get(alternatif_id), if_match, settings.require_if_match)
    item = service.update(alternatif_id, data, pelaku_kode_orang=pelaku)
    response.headers["ETag"] = compute_etag(item)
    return item
