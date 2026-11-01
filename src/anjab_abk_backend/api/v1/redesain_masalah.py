"""Endpoint masalah redesain (sheet MASALAH): khusus `tim-kajian`, tanpa DELETE."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from ...dependencies import (
    READ_GUARDS,
    Pagination,
    get_kode_orang_pemanggil,
    get_masalah_service,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...redesain.schemas.masalah import (
    MasalahCreate,
    MasalahRead,
    MasalahStatusKonfirmasi,
    MasalahUpdate,
)
from ...redesain.services.masalah import MasalahService
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Masalah tidak ditemukan."}}
_INVALID = {
    422: {
        "model": ErrorResponse,
        "description": "Payload tidak valid / konteks, sekolah, atau uraian tugas tak dikenal.",
    }
}


@router.get(
    "",
    response_model=Page[MasalahRead],
    summary="Daftar masalah redesain (tim-kajian)",
    operation_id="redesain_masalah_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_masalah(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[MasalahService, Depends(get_masalah_service)],
) -> Page[MasalahRead]:
    """Daftar masalah berurutan menurut kode."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[MasalahRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=MasalahRead,
    status_code=201,
    summary="Tambah masalah redesain (tim-kajian)",
    operation_id="redesain_masalah_create",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_INVALID,
        409: {"model": ErrorResponse, "description": "Kode masalah bentrok."},
    },
)
def create_masalah(
    data: MasalahCreate,
    service: Annotated[MasalahService, Depends(get_masalah_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> MasalahRead:
    """Buat masalah baru; `kode` dibangkitkan dari kode konteks (`K-01` → `M-K01-NN`).

    `uraian_tugas_ids` divalidasi lewat seam katalog Task Inventory; ID tak dikenal → 422
    tanpa satu baris pun tertulis. Riwayat `entitas="masalah"` dicatat.
    """
    return service.create(data, pelaku_kode_orang=pelaku)


@router.post(
    "/search",
    response_model=Page[MasalahRead],
    summary="Cari masalah (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_masalah_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_masalah(
    req: SearchRequest,
    service: Annotated[MasalahService, Depends(get_masalah_service)],
) -> Page[MasalahRead]:
    """Cari dengan domain ala Odoo; field: kode, konteks_id, sekolah_id, status_awal, eskalasi_pada,
    gelombang, dibuka_untuk_konfirmasi."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[MasalahRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{masalah_id}",
    response_model=MasalahRead,
    summary="Detail masalah redesain (tim-kajian)",
    operation_id="redesain_masalah_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_masalah(
    masalah_id: str,
    service: Annotated[MasalahService, Depends(get_masalah_service)],
) -> MasalahRead:
    """Ambil satu masalah beserta `uraian_tugas_ids`."""
    return service.get(masalah_id)


@router.patch(
    "/{masalah_id}",
    response_model=MasalahRead,
    summary="Ubah masalah redesain (tim-kajian)",
    operation_id="redesain_masalah_update",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        **_INVALID,
        409: {"model": ErrorResponse, "description": "Status awal sudah dibekukan."},
    },
)
def update_masalah(
    masalah_id: str,
    data: MasalahUpdate,
    service: Annotated[MasalahService, Depends(get_masalah_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> MasalahRead:
    """Ubah parsial masalah; `uraian_tugas_ids` (bila dikirim) mengganti penuh tautan.

    `kode` & `status_awal_dibekukan_pada` read-only; `status_awal` ditolak 409 bila sudah
    dibekukan (field lain tetap boleh).
    """
    return service.update(masalah_id, data, pelaku_kode_orang=pelaku)


@router.post(
    "/{masalah_id}/status-konfirmasi",
    response_model=MasalahRead,
    summary="Buka/tutup masalah untuk konfirmasi sekolah (tim-kajian)",
    operation_id="redesain_masalah_status_konfirmasi",
    dependencies=_WRITE,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def status_konfirmasi_masalah(
    masalah_id: str,
    data: MasalahStatusKonfirmasi,
    service: Annotated[MasalahService, Depends(get_masalah_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
) -> MasalahRead:
    """Set `dibuka_untuk_konfirmasi` sesuai `dibuka` dan catat riwayat."""
    return service.set_status_konfirmasi(masalah_id, data.dibuka, pelaku_kode_orang=pelaku)
