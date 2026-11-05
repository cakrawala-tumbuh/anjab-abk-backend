"""Endpoint sumber narasi: khusus `tim-kajian`, tanpa PATCH/DELETE (baris tak berubah)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    SessionDep,
    get_current_principal,
    get_narasi_sumber_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...narasi.schemas.sumber import (
    JenisSumberNarasi,
    NarasiSumberCreate,
    NarasiSumberRead,
    NarasiSumberRingkas,
)
from ...narasi.schemas.uji_kering import UjiKeringRead, UjiKeringRequest
from ...narasi.services.sumber import NarasiSumberService
from ...narasi.services.uji_kering import jalankan_uji_kering
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ...security import Principal
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Sumber narasi tidak ditemukan."}}


@router.get(
    "",
    response_model=Page[NarasiSumberRingkas],
    summary="Daftar sumber narasi tanpa teks (tim-kajian)",
    operation_id="narasi_sumber_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_sumber(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[NarasiSumberService, Depends(get_narasi_sumber_service)],
    jenis: Annotated[JenisSumberNarasi | None, Query(description="Filter jenis.")] = None,
    periode: Annotated[str | None, Query(max_length=20, description="Filter periode.")] = None,
) -> Page[NarasiSumberRingkas]:
    """Daftar ringkas (tanpa `teks`), terbaru dulu; filter `jenis` dan `periode`."""
    items, total = service.list(
        jenis=jenis.value if jenis else None,
        periode=periode,
        limit=page.limit,
        offset=page.offset,
    )
    return Page[NarasiSumberRingkas](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=NarasiSumberRead,
    status_code=201,
    summary="Simpan sumber narasi baru (tim-kajian)",
    operation_id="narasi_sumber_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def create_sumber(
    data: NarasiSumberCreate,
    service: Annotated[NarasiSumberService, Depends(get_narasi_sumber_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> NarasiSumberRead:
    """Simpan teks sumber (tak dapat diubah); `dibuat_oleh` diambil dari token.

    Revisi teks atau perubahan izin dibuat sebagai baris baru dengan `menggantikan_id`.
    """

    def _aksi() -> NarasiSumberRead:
        return service.create(data, dibuat_oleh=principal.subject)

    return run_idempotent(idem, response, NarasiSumberRead, _aksi)


@router.post(
    "/search",
    response_model=Page[NarasiSumberRingkas],
    summary="Cari sumber narasi (domain ala Odoo) (tim-kajian)",
    operation_id="narasi_sumber_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_sumber(
    req: SearchRequest,
    service: Annotated[NarasiSumberService, Depends(get_narasi_sumber_service)],
) -> Page[NarasiSumberRingkas]:
    """Cari dengan domain ala Odoo; field di-whitelist; hasil tanpa `teks`."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[NarasiSumberRingkas](items=items, total=total, limit=req.limit, offset=req.offset)


@router.post(
    "/uji-kering",
    response_model=UjiKeringRead,
    summary="Uji kering gerbang PII atas sumber narasi (tim-kajian)",
    operation_id="narasi_sumber_uji_kering",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {
            "model": ErrorResponse,
            "description": "Id tak dikenal atau lebih dari 500 sumber (uji_kering_terlalu_banyak).",
        },
    },
)
def uji_kering_sumber(
    req: UjiKeringRequest,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
) -> UjiKeringRead:
    """Hitung berapa sumber ditolak gerbang PII (mode BLOKIR) dan mengapa.

    Tanpa model, tanpa tulisan, dan tanpa nilai PII pada respons. Berjalan walau flag AI mati.
    """
    return jalankan_uji_kering(session, settings, req.sumber_ids)


@router.get(
    "/{sumber_id}",
    response_model=NarasiSumberRead,
    summary="Detail sumber narasi beserta teks (tim-kajian)",
    operation_id="narasi_sumber_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_sumber(
    sumber_id: str,
    service: Annotated[NarasiSumberService, Depends(get_narasi_sumber_service)],
) -> NarasiSumberRead:
    """Ambil satu sumber lengkap dengan `teks`."""
    return service.get(sumber_id)
