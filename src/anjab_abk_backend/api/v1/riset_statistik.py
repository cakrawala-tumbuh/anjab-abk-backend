"""Endpoint statistik riset: khusus `tim-kajian`, tanpa sunting maupun hapus.

Statistik dicatat per protokol `TERKUNCI` dan menjadi `TERVERIFIKASI` hanya bila diverifikasi
subjek token yang berbeda dari pengunggahnya. Koreksi = statistik baru; tidak ada endpoint
sunting, hapus, maupun pembatalan verifikasi.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_current_principal,
    get_riset_statistik_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...schemas.common import ErrorResponse, Page
from ...schemas.riset_statistik import RisetStatistikCreate, RisetStatistikRead, StatusStatistik
from ...security import Principal
from ...services.riset_statistik import RisetStatistikService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_PROTOKOL_404 = {404: {"model": ErrorResponse, "description": "Protokol riset tidak ditemukan."}}


@router.get(
    "/protokol/{protokol_id}/statistik",
    response_model=Page[RisetStatistikRead],
    summary="Daftar statistik satu protokol riset (tim-kajian)",
    operation_id="riset_statistik_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_PROTOKOL_404},
)
def list_statistik(
    protokol_id: str,
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[RisetStatistikService, Depends(get_riset_statistik_service)],
    status: Annotated[StatusStatistik | None, Query(description="Filter status.")] = None,
) -> Page[RisetStatistikRead]:
    """Daftar statistik milik protokol, terbaru dulu; filter `status` opsional."""
    items, total = service.list_by_protokol(
        protokol_id,
        status=status.value if status else None,
        limit=page.limit,
        offset=page.offset,
    )
    return Page[RisetStatistikRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "/protokol/{protokol_id}/statistik",
    response_model=RisetStatistikRead,
    status_code=201,
    summary="Catat statistik riset untuk protokol terkunci (tim-kajian)",
    operation_id="riset_statistik_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_PROTOKOL_404,
        409: {
            "model": ErrorResponse,
            "description": "Protokol masih DRAF (`PROTOKOL_BELUM_TERKUNCI`).",
        },
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def create_statistik(
    protokol_id: str,
    data: RisetStatistikCreate,
    service: Annotated[RisetStatistikService, Depends(get_riset_statistik_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> RisetStatistikRead:
    """Simpan statistik `DRAF`; pengunggah (`dibuat_oleh`) selalu subjek token.

    Hanya protokol `TERKUNCI` yang boleh menjadi dasar; tidak ada sunting sesudahnya.
    """

    def _aksi() -> RisetStatistikRead:
        return service.create(protokol_id, data, dibuat_oleh=principal.subject)

    return run_idempotent(idem, response, RisetStatistikRead, _aksi)


@router.post(
    "/statistik/{statistik_id}/verifikasi",
    response_model=RisetStatistikRead,
    summary="Verifikasi statistik riset oleh subjek independen (tim-kajian)",
    operation_id="riset_statistik_verifikasi",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Statistik riset tidak ditemukan."},
        409: {
            "model": ErrorResponse,
            "description": (
                "Sudah terverifikasi (`STATISTIK_SUDAH_TERVERIFIKASI`) atau pemverifikasi "
                "adalah pengunggahnya (`PEMVERIFIKASI_TIDAK_INDEPENDEN`)."
            ),
        },
    },
)
def verifikasi_statistik(
    statistik_id: str,
    service: Annotated[RisetStatistikService, Depends(get_riset_statistik_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> RisetStatistikRead:
    """Set `TERVERIFIKASI`, `diverifikasi_oleh` (subjek token), dan `diverifikasi_pada`.

    Pemverifikasi wajib berbeda dari `dibuat_oleh`; verifikasi tidak dapat diulang atau dibatalkan.
    """
    return service.verifikasi(statistik_id, diverifikasi_oleh=principal.subject)
