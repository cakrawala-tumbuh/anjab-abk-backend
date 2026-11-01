"""Endpoint baca ringkasan yayasan (sheet YAYASAN): khusus `tim-kajian`, read-model tanpa tulis."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...dependencies import (
    READ_GUARDS,
    Pagination,
    get_ringkasan_yayasan_service,
    pagination_params,
    require_tim_kajian,
)
from ...redesain.schemas.yayasan import RingkasanYayasanRow
from ...redesain.services.yayasan import RingkasanYayasanService
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Masalah tidak ditemukan."}}


@router.get(
    "",
    response_model=Page[RingkasanYayasanRow],
    summary="Ringkasan yayasan per masalah (tim-kajian)",
    operation_id="redesain_yayasan_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_yayasan(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[RingkasanYayasanService, Depends(get_ringkasan_yayasan_service)],
) -> Page[RingkasanYayasanRow]:
    """Daftar ringkasan yayasan, satu baris per masalah, berurutan menurut kode masalah."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[RingkasanYayasanRow](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "/search",
    response_model=Page[RingkasanYayasanRow],
    summary="Cari ringkasan yayasan (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_yayasan_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_yayasan(
    req: SearchRequest,
    service: Annotated[RingkasanYayasanService, Depends(get_ringkasan_yayasan_service)],
) -> Page[RingkasanYayasanRow]:
    """Cari dengan domain ala Odoo; field di-whitelist, nilai bound parameter."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[RingkasanYayasanRow](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{masalah_id}",
    response_model=RingkasanYayasanRow,
    summary="Detail ringkasan yayasan satu masalah (tim-kajian)",
    operation_id="redesain_yayasan_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_yayasan(
    masalah_id: str,
    service: Annotated[RingkasanYayasanService, Depends(get_ringkasan_yayasan_service)],
) -> RingkasanYayasanRow:
    """Ambil ringkasan satu masalah; field penilaian `null` bila belum dinilai."""
    return service.get(masalah_id)
