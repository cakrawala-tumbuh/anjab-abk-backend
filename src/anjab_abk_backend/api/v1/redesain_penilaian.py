"""Endpoint penilaian redesain + saran triase otomatis: khusus `tim-kajian`, tanpa DELETE."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_kode_orang_pemanggil,
    get_penilaian_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...etag import check_if_match, compute_etag
from ...redesain.schemas.penilaian import (
    PenilaianCreate,
    PenilaianPutuskan,
    PenilaianRead,
    PenilaianStatus,
    PenilaianUpdate,
)
from ...redesain.services.penilaian import PenilaianService
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
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Penilaian tidak ditemukan."}}


@router.get(
    "",
    response_model=Page[PenilaianRead],
    summary="Daftar penilaian redesain (tim-kajian)",
    operation_id="redesain_penilaian_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_penilaian(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[PenilaianService, Depends(get_penilaian_service)],
) -> Page[PenilaianRead]:
    """Daftar penilaian berurutan menurut waktu dibuat."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[PenilaianRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=PenilaianRead,
    status_code=201,
    summary="Tambah penilaian redesain (tim-kajian)",
    operation_id="redesain_penilaian_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {"model": ErrorResponse, "description": "Masalah sudah punya penilaian."},
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def create_penilaian(
    data: PenilaianCreate,
    service: Annotated[PenilaianService, Depends(get_penilaian_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> PenilaianRead:
    """Buat penilaian satu masalah; `saran_otomatis` dihitung sistem, 409 bila sudah ada."""

    def _aksi() -> PenilaianRead:
        return service.create(data, pelaku_kode_orang=pelaku)

    return run_idempotent(idem, response, PenilaianRead, _aksi)


@router.post(
    "/search",
    response_model=Page[PenilaianRead],
    summary="Cari penilaian (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_penilaian_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_penilaian(
    req: SearchRequest,
    service: Annotated[PenilaianService, Depends(get_penilaian_service)],
) -> Page[PenilaianRead]:
    """Cari dengan domain ala Odoo; field di-whitelist, nilai bound parameter."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[PenilaianRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/agenda-yayasan",
    response_model=Page[PenilaianRead],
    summary="Agenda telaah yayasan: penilaian berstatus siap (tim-kajian)",
    operation_id="redesain_penilaian_agenda_yayasan",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def agenda_yayasan(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[PenilaianService, Depends(get_penilaian_service)],
) -> Page[PenilaianRead]:
    """Daftar penilaian berstatus `Siap untuk telaah yayasan` (bahan ekspor ringkasan)."""
    items, total = service.agenda_yayasan(limit=page.limit, offset=page.offset)
    return Page[PenilaianRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.get(
    "/{penilaian_id}",
    response_model=PenilaianRead,
    summary="Detail penilaian redesain (tim-kajian)",
    operation_id="redesain_penilaian_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_penilaian(
    penilaian_id: str,
    service: Annotated[PenilaianService, Depends(get_penilaian_service)],
    response: Response,
) -> PenilaianRead:
    """Ambil satu penilaian."""
    item = service.get(penilaian_id)
    response.headers["ETag"] = compute_etag(item)
    return item


@router.patch(
    "/{penilaian_id}",
    response_model=PenilaianRead,
    summary="Ubah penilaian redesain (tim-kajian)",
    operation_id="redesain_penilaian_update",
    dependencies=_WRITE,
    responses={**PRECONDITION_RESPONSES, **_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def update_penilaian(
    penilaian_id: str,
    data: PenilaianUpdate,
    service: Annotated[PenilaianService, Depends(get_penilaian_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: IfMatchHeader = None,
) -> PenilaianRead:
    """Ubah parsial penilaian; `saran_otomatis` dihitung ulang, `masalah_id` tetap."""
    check_if_match(service.get(penilaian_id), if_match, settings.require_if_match)
    item = service.update(penilaian_id, data, pelaku_kode_orang=pelaku)
    response.headers["ETag"] = compute_etag(item)
    return item


@router.post(
    "/{penilaian_id}/putuskan",
    response_model=PenilaianRead,
    summary="Putuskan prioritas final penilaian (tim-kajian)",
    operation_id="redesain_penilaian_putuskan",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        422: {"model": ErrorResponse, "description": "Alasan/pemutus/tanggal tidak valid."},
    },
)
def putuskan_penilaian(
    penilaian_id: str,
    data: PenilaianPutuskan,
    service: Annotated[PenilaianService, Depends(get_penilaian_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> PenilaianRead:
    """Catat prioritas final beserta alasan, pemutus, dan tanggal; peringatan tidak memblokir."""

    def _aksi() -> PenilaianRead:
        return service.putuskan(penilaian_id, data, pelaku_kode_orang=pelaku)

    return run_idempotent(idem, response, PenilaianRead, _aksi)


@router.post(
    "/{penilaian_id}/status",
    response_model=PenilaianRead,
    summary="Ubah status penilaian (tim-kajian)",
    operation_id="redesain_penilaian_status",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        422: {"model": ErrorResponse, "description": "Status tidak valid (mis. Telah diputuskan)."},
    },
)
def ubah_status_penilaian(
    penilaian_id: str,
    data: PenilaianStatus,
    service: Annotated[PenilaianService, Depends(get_penilaian_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> PenilaianRead:
    """Ubah `status_penilaian` ke salah satu dari empat status selain `Telah diputuskan`."""

    def _aksi() -> PenilaianRead:
        return service.set_status(penilaian_id, data, pelaku_kode_orang=pelaku)

    return run_idempotent(idem, response, PenilaianRead, _aksi)
