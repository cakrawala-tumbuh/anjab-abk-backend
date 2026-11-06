"""Endpoint baca usulan AI non-narasi: khusus `tim-kajian`, tanpa PATCH/DELETE."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_ai_usulan_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...schemas.ai_usulan import (
    AiUsulanPutusanCreate,
    AiUsulanPutusanRead,
    AiUsulanRead,
    AiUsulanRingkas,
    HasilSerapUsulan,
    SasaranUsulan,
)
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ...security import Principal
from ...services.ai_usulan import AiUsulanService
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
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


@router.post(
    "/{usulan_id}/putusan",
    response_model=AiUsulanPutusanRead,
    status_code=201,
    summary="Catat putusan reviewer atas usulan AI (tim-kajian)",
    operation_id="ai_usulan_putusan_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        409: {
            "model": ErrorResponse,
            "description": (
                "`usulan_belum_bisa_diputus` (belum diserap atau `MANUAL`) atau "
                "Idempotency-Key ini sedang diproses."
            ),
        },
        422: {"model": ErrorResponse, "description": "Payload atau kombinasi putusan tidak valid."},
    },
)
def create_putusan(
    usulan_id: str,
    data: AiUsulanPutusanCreate,
    service: Annotated[AiUsulanService, Depends(get_ai_usulan_service)],
    principal: Annotated[Principal, Depends(require_tim_kajian)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> AiUsulanPutusanRead:
    """Catat putusan `APPROVE`/`REVISE`/`REJECT` (append-only); aktor dari token.

    Hanya catatan audit: tidak menulis `narasi_*`, tidak mengubah status kasus, tidak
    mengirim apa pun. Putusan berulang boleh; yang terbaru menjadi `putusan_terakhir`.
    Pemeriksaan 404/409 berada di dalam aksi idempoten, jadi ulangan dengan key yang sama
    membalas respons tersimpan (200), bukan galat.
    """

    def _aksi() -> AiUsulanPutusanRead:
        return service.putuskan(usulan_id, data, principal.subject)

    return run_idempotent(idem, response, AiUsulanPutusanRead, _aksi)
