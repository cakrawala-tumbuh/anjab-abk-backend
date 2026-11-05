"""Endpoint baca usulan AI non-narasi: khusus `tim-kajian`, tanpa PATCH/DELETE."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ...dependencies import (
    READ_GUARDS,
    Pagination,
    get_ai_usulan_service,
    pagination_params,
    require_tim_kajian,
)
from ...schemas.ai_usulan import AiUsulanRead, AiUsulanRingkas, HasilSerapUsulan, SasaranUsulan
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ...services.ai_usulan import AiUsulanService

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Usulan AI tidak ditemukan."}}


@router.get(
    "",
    response_model=Page[AiUsulanRingkas],
    summary="Daftar usulan AI tanpa isi (tim-kajian)",
    operation_id="ai_usulan_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_usulan(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
    fungsi: Annotated[str | None, Query(max_length=10, description="Filter kode fungsi.")] = None,
    sasaran_jenis: Annotated[
        SasaranUsulan | None, Query(description="Filter jenis sasaran.")
    ] = None,
    sasaran_id: Annotated[
        str | None, Query(max_length=36, description="Filter id sasaran.")
    ] = None,
    hasil_serap: Annotated[
        HasilSerapUsulan | None, Query(description="Filter hasil serap.")
    ] = None,
) -> Page[AiUsulanRingkas]:
    """Daftar ringkas (tanpa `isi` dan `amplop`), terbaru dulu."""
    items, total = service.list(
        fungsi=fungsi,
        sasaran_jenis=sasaran_jenis.value if sasaran_jenis else None,
        sasaran_id=sasaran_id,
        hasil_serap=hasil_serap.value if hasil_serap else None,
        limit=page.limit,
        offset=page.offset,
    )
    return Page[AiUsulanRingkas](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "/search",
    response_model=Page[AiUsulanRingkas],
    summary="Cari usulan AI (domain ala Odoo) (tim-kajian)",
    operation_id="ai_usulan_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_usulan(
    req: SearchRequest,
    service: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
) -> Page[AiUsulanRingkas]:
    """Cari dengan domain ala Odoo; field di-whitelist; hasil tanpa `isi` dan `amplop`."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[AiUsulanRingkas](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{usulan_id}",
    response_model=AiUsulanRead,
    summary="Detail usulan AI beserta isi dan amplop (tim-kajian)",
    operation_id="ai_usulan_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_usulan(
    usulan_id: str,
    service: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
) -> AiUsulanRead:
    """Ambil satu usulan lengkap dengan `isi`, `amplop`, dan `output_hash`."""
    return service.get(usulan_id)
