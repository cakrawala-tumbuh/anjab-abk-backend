"""Endpoint cakupan jabatan redesain (CAKUPAN_19): khusus `tim-kajian`, tanpa DELETE."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_cakupan_jabatan_service,
    get_kode_orang_pemanggil,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...etag import check_if_match, compute_etag
from ...redesain.schemas.cakupan_jabatan import (
    CakupanJabatanCreate,
    CakupanJabatanRead,
    CakupanJabatanUpdate,
)
from ...redesain.services.cakupan_jabatan import CakupanJabatanService
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
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Cakupan jabatan tidak ditemukan."}}


@router.get(
    "",
    response_model=Page[CakupanJabatanRead],
    summary="Daftar cakupan jabatan redesain (tim-kajian)",
    operation_id="redesain_cakupan_jabatan_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_cakupan(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[CakupanJabatanService, Depends(get_cakupan_jabatan_service)],
) -> Page[CakupanJabatanRead]:
    """Daftar cakupan jabatan berurutan menurut role_kode lalu cabang."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[CakupanJabatanRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=CakupanJabatanRead,
    status_code=201,
    summary="Tambah cakupan jabatan redesain (tim-kajian)",
    operation_id="redesain_cakupan_jabatan_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {"model": ErrorResponse, "description": "Pasangan role_kode dan cabang sudah ada."},
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def create_cakupan(
    data: CakupanJabatanCreate,
    service: Annotated[CakupanJabatanService, Depends(get_cakupan_jabatan_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> CakupanJabatanRead:
    """Buat entri cakupan; 409 bila pasangan role_kode+cabang ada, 422 bila jabatan tak dikenal."""

    def _aksi() -> CakupanJabatanRead:
        return service.create(data, pelaku_kode_orang=pelaku)

    return run_idempotent(idem, response, CakupanJabatanRead, _aksi)


@router.post(
    "/search",
    response_model=Page[CakupanJabatanRead],
    summary="Cari cakupan jabatan (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_cakupan_jabatan_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_cakupan(
    req: SearchRequest,
    service: Annotated[CakupanJabatanService, Depends(get_cakupan_jabatan_service)],
) -> Page[CakupanJabatanRead]:
    """Cari dengan domain ala Odoo; field di-whitelist, nilai bound parameter."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[CakupanJabatanRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{cakupan_id}",
    response_model=CakupanJabatanRead,
    summary="Detail cakupan jabatan redesain (tim-kajian)",
    operation_id="redesain_cakupan_jabatan_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_cakupan(
    cakupan_id: str,
    service: Annotated[CakupanJabatanService, Depends(get_cakupan_jabatan_service)],
    response: Response,
) -> CakupanJabatanRead:
    """Ambil satu entri cakupan jabatan."""
    item = service.get(cakupan_id)
    response.headers["ETag"] = compute_etag(item)
    return item


@router.patch(
    "/{cakupan_id}",
    response_model=CakupanJabatanRead,
    summary="Ubah cakupan jabatan redesain (tim-kajian)",
    operation_id="redesain_cakupan_jabatan_update",
    dependencies=_WRITE,
    responses={**PRECONDITION_RESPONSES, **_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def update_cakupan(
    cakupan_id: str,
    data: CakupanJabatanUpdate,
    service: Annotated[CakupanJabatanService, Depends(get_cakupan_jabatan_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: IfMatchHeader = None,
) -> CakupanJabatanRead:
    """Ubah parsial entri (mis. status, pemetaan jabatan_id); role_kode dan cabang tetap."""
    check_if_match(service.get(cakupan_id), if_match, settings.require_if_match)
    item = service.update(cakupan_id, data, pelaku_kode_orang=pelaku)
    response.headers["ETag"] = compute_etag(item)
    return item
