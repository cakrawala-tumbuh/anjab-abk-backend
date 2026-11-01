"""Endpoint proses & langkah redesain (sheet ALUR): khusus `tim-kajian`, tanpa DELETE.

Dua router: `router` di-mount ke `/redesain/proses` dan `router_langkah` ke
`/redesain/langkah`. Langkah yang tak berlaku diberi status `Tidak berlaku`, tidak dihapus.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...dependencies import (
    READ_GUARDS,
    Pagination,
    get_kode_orang_pemanggil,
    get_proses_service,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...redesain.schemas.proses import (
    LangkahCreate,
    LangkahRead,
    LangkahUpdate,
    ProsesCreate,
    ProsesRead,
    ProsesUpdate,
)
from ...redesain.services.proses import ProsesService
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest

router = APIRouter()
router_langkah = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Proses tidak ditemukan."}}
_INVALID = {
    422: {
        "model": ErrorResponse,
        "description": (
            "Payload tidak valid / masalah atau sekolah tak dikenal / sekolah proses "
            "berbeda dari sekolah masalah."
        ),
    }
}
_CONFLICT = {409: {"model": ErrorResponse, "description": "Kode hasil bangkitan bentrok."}}


@router.get(
    "",
    response_model=Page[ProsesRead],
    summary="Daftar proses redesain (tim-kajian)",
    operation_id="redesain_proses_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_proses(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[ProsesService, Depends(get_proses_service)],
) -> Page[ProsesRead]:
    """Daftar proses berurutan menurut kode, masing-masing beserta langkahnya."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[ProsesRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=ProsesRead,
    status_code=201,
    summary="Tambah proses redesain (tim-kajian)",
    operation_id="redesain_proses_create",
    dependencies=_WRITE,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_INVALID, **_CONFLICT},
)
def create_proses(
    data: ProsesCreate,
    service: Annotated[ProsesService, Depends(get_proses_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> ProsesRead:
    """Buat proses baru untuk satu masalah × sekolah; `kode` dibangkitkan global (`P-001`).

    `sekolah_id` wajib sama dengan `masalah.sekolah_id` bila masalah sudah bersekolah;
    masalah tanpa sekolah menerima sekolah mana pun. Selisih → 422. Riwayat
    `entitas="proses"` dicatat.
    """
    return service.create(data, pelaku_kode_orang=pelaku)


@router.post(
    "/search",
    response_model=Page[ProsesRead],
    summary="Cari proses (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_proses_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_proses(
    req: SearchRequest,
    service: Annotated[ProsesService, Depends(get_proses_service)],
) -> Page[ProsesRead]:
    """Cari dengan domain ala Odoo; field: masalah_id, sekolah_id, kode."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[ProsesRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{proses_id}",
    response_model=ProsesRead,
    summary="Detail proses redesain beserta langkah (tim-kajian)",
    operation_id="redesain_proses_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_proses(
    proses_id: str,
    service: Annotated[ProsesService, Depends(get_proses_service)],
) -> ProsesRead:
    """Ambil satu proses beserta `langkah` terurut `urutan`."""
    return service.get(proses_id)


@router.patch(
    "/{proses_id}",
    response_model=ProsesRead,
    summary="Ubah proses redesain (tim-kajian)",
    operation_id="redesain_proses_update",
    dependencies=_WRITE,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND, **_INVALID},
)
def update_proses(
    proses_id: str,
    data: ProsesUpdate,
    service: Annotated[ProsesService, Depends(get_proses_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> ProsesRead:
    """Ubah parsial proses; `kode` read-only, aturan sekolah↔masalah divalidasi ulang."""
    return service.update(proses_id, data, pelaku_kode_orang=pelaku)


@router.post(
    "/{proses_id}/langkah",
    response_model=LangkahRead,
    status_code=201,
    summary="Tambah langkah pada proses redesain (tim-kajian)",
    operation_id="redesain_langkah_create",
    dependencies=_WRITE,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND, **_CONFLICT},
)
def create_langkah(
    proses_id: str,
    data: LangkahCreate,
    service: Annotated[ProsesService, Depends(get_proses_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> LangkahRead:
    """Tambah langkah; `kode` dibangkitkan per proses (`P-001-S01`, `-S02`, ...).

    `status_langkah` wajib dari kosakata `StatusLangkah` (nilai lain → 422). Riwayat
    `entitas="langkah"` dicatat.
    """
    return service.tambah_langkah(proses_id, data, pelaku_kode_orang=pelaku)


@router_langkah.patch(
    "/{langkah_id}",
    response_model=LangkahRead,
    summary="Ubah langkah proses redesain (tim-kajian)",
    operation_id="redesain_langkah_update",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Langkah tidak ditemukan."},
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def update_langkah(
    langkah_id: str,
    data: LangkahUpdate,
    service: Annotated[ProsesService, Depends(get_proses_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> LangkahRead:
    """Ubah parsial langkah; `kode`/`proses_id` read-only. Riwayat dicatat."""
    return service.update_langkah(langkah_id, data, pelaku_kode_orang=pelaku)
