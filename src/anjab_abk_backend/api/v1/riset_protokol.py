"""Endpoint protokol riset: khusus `tim-kajian`, tanpa PATCH/PUT/DELETE.

Revisi = protokol `DRAF` baru dengan `kode` sama (versi naik); `kunci` membekukan protokol
permanen beserta `isi_hash`. Tidak ada endpoint buka-kunci maupun hapus (jejak audit).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_current_principal,
    get_riset_protokol_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...schemas.common import ErrorResponse, Page
from ...schemas.riset_protokol import (
    POLA_KODE_PROTOKOL,
    RisetProtokolCreate,
    RisetProtokolRead,
    RisetProtokolRingkas,
    StatusProtokol,
)
from ...security import Principal
from ...services.riset_protokol import RisetProtokolService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Protokol riset tidak ditemukan."}}


@router.get(
    "",
    response_model=Page[RisetProtokolRingkas],
    summary="Daftar protokol riset tanpa isi (tim-kajian)",
    operation_id="riset_protokol_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_protokol(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[RisetProtokolService, Depends(get_riset_protokol_service)],
    kode: Annotated[
        str | None,
        Query(max_length=40, pattern=POLA_KODE_PROTOKOL, description="Filter kode protokol."),
    ] = None,
    status: Annotated[StatusProtokol | None, Query(description="Filter status.")] = None,
) -> Page[RisetProtokolRingkas]:
    """Daftar ringkas (tanpa `isi`), terbaru dulu; filter `kode` dan `status`."""
    items, total = service.list(
        kode=kode,
        status=status.value if status else None,
        limit=page.limit,
        offset=page.offset,
    )
    return Page[RisetProtokolRingkas](
        items=items, total=total, limit=page.limit, offset=page.offset
    )


@router.post(
    "",
    response_model=RisetProtokolRead,
    status_code=201,
    summary="Simpan protokol riset baru berstatus DRAF (tim-kajian)",
    operation_id="riset_protokol_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {"model": ErrorResponse, "description": "Versi bentrok dengan permintaan bersamaan."},
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def create_protokol(
    data: RisetProtokolCreate,
    service: Annotated[RisetProtokolService, Depends(get_riset_protokol_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> RisetProtokolRead:
    """Simpan protokol `DRAF`; `versi` = versi terbesar `kode` itu + 1, pembuat dari token.

    Tidak ada sunting: perbaikan draf maupun revisi dibuat sebagai protokol baru berkode sama.
    """

    def _aksi() -> RisetProtokolRead:
        return service.create(data, dibuat_oleh=principal.subject)

    return run_idempotent(idem, response, RisetProtokolRead, _aksi)


@router.get(
    "/{protokol_id}",
    response_model=RisetProtokolRead,
    summary="Detail protokol riset beserta isi (tim-kajian)",
    operation_id="riset_protokol_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_protokol(
    protokol_id: str,
    service: Annotated[RisetProtokolService, Depends(get_riset_protokol_service)],
) -> RisetProtokolRead:
    """Ambil satu protokol lengkap dengan `isi`."""
    return service.get(protokol_id)


@router.post(
    "/{protokol_id}/kunci",
    response_model=RisetProtokolRead,
    summary="Kunci protokol riset secara permanen (tim-kajian)",
    operation_id="riset_protokol_kunci",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        409: {
            "model": ErrorResponse,
            "description": "Protokol sudah terkunci (`PROTOKOL_TERKUNCI`).",
        },
    },
)
def kunci_protokol(
    protokol_id: str,
    service: Annotated[RisetProtokolService, Depends(get_riset_protokol_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> RisetProtokolRead:
    """Set `TERKUNCI`, `isi_hash` = SHA-256 heksadesimal `isi`, `dikunci_oleh` dari token.

    Sesudah terkunci tidak ada jalur API yang mengubah baris; kunci ulang dibalas 409.
    """
    return service.kunci(protokol_id, dikunci_oleh=principal.subject)
