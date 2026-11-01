"""Endpoint sesi partisipasi redesain: khusus `tim-kajian`, tanpa DELETE dan tanpa gerbang izin."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...dependencies import (
    READ_GUARDS,
    Pagination,
    get_kode_orang_pemanggil,
    get_sesi_service,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...redesain.schemas.sesi import RekapOrangRead, SesiCreate, SesiRead, SesiUpdate
from ...redesain.services.sesi import SesiService
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Sesi tidak ditemukan."}}
_CONFLICT = {409: {"model": ErrorResponse, "description": "Pasangan kode sesi + orang ganda."}}
_INVALID = {422: {"model": ErrorResponse, "description": "Payload/rujukan tidak valid."}}


@router.get(
    "",
    response_model=Page[SesiRead],
    summary="Daftar sesi partisipasi (tim-kajian)",
    operation_id="redesain_sesi_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_sesi(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[SesiService, Depends(get_sesi_service)],
) -> Page[SesiRead]:
    """Daftar baris orang × sesi berurutan menurut kode sesi lalu kode orang."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[SesiRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=SesiRead,
    status_code=201,
    summary="Catat keterlibatan orang pada sesi (tim-kajian)",
    operation_id="redesain_sesi_create",
    dependencies=_WRITE,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_CONFLICT, **_INVALID},
)
def create_sesi(
    data: SesiCreate,
    service: Annotated[SesiService, Depends(get_sesi_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> SesiRead:
    """Catat satu orang × satu sesi; `status_izin` apa pun (juga `Tidak diotorisasi`) diterima."""
    return service.create(data, pelaku_kode_orang=pelaku)


@router.post(
    "/search",
    response_model=Page[SesiRead],
    summary="Cari sesi partisipasi (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_sesi_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_sesi(
    req: SearchRequest,
    service: Annotated[SesiService, Depends(get_sesi_service)],
) -> Page[SesiRead]:
    """Cari dengan domain ala Odoo (`kode_sesi`, `kode_orang`, `jenis_kegiatan`, `status_izin`)."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[SesiRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/rekap-orang",
    response_model=Page[RekapOrangRead],
    summary="Rekap menit keterlibatan per orang unik (tim-kajian)",
    operation_id="redesain_sesi_rekap_orang",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def rekap_orang(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[SesiService, Depends(get_sesi_service)],
) -> Page[RekapOrangRead]:
    """Per kode orang: jumlah sesi berbeda dan total menit (NULL diabaikan; semua NULL → null)."""
    items, total = service.rekap_orang(limit=page.limit, offset=page.offset)
    return Page[RekapOrangRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.get(
    "/{sesi_id}",
    response_model=SesiRead,
    summary="Detail sesi partisipasi (tim-kajian)",
    operation_id="redesain_sesi_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_sesi(
    sesi_id: str,
    service: Annotated[SesiService, Depends(get_sesi_service)],
) -> SesiRead:
    """Ambil satu baris sesi beserta `masalah_ids`."""
    return service.get(sesi_id)


@router.patch(
    "/{sesi_id}",
    response_model=SesiRead,
    summary="Ubah sesi partisipasi (tim-kajian)",
    operation_id="redesain_sesi_update",
    dependencies=_WRITE,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND, **_CONFLICT, **_INVALID},
)
def update_sesi(
    sesi_id: str,
    data: SesiUpdate,
    service: Annotated[SesiService, Depends(get_sesi_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> SesiRead:
    """Ubah parsial; `masalah_ids` yang dikirim mengganti seluruh tautan masalah."""
    return service.update(sesi_id, data, pelaku_kode_orang=pelaku)
