"""Endpoint resource `detil-tugas`: CRUD + search (master data catalog TI)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Path, Request, Response, status

from ...config import Settings, get_settings
from ...dependencies import (
    Idempotency,
    Pagination,
    get_current_principal,
    get_detil_tugas_service,
    idempotency,
    pagination_params,
    rate_limit,
)
from ...errors import ConflictError, PreconditionFailedError, PreconditionRequiredError
from ...etag import compute_etag
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ...taskinv.schemas.detil_tugas import DetilTugasCreate, DetilTugasRead, DetilTugasUpdate
from ...taskinv.services.detil_tugas import DetilTugasService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "DetilTugas tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_PRECONDITION = {
    412: {"model": ErrorResponse, "description": "If-Match tidak cocok."},
    428: {"model": ErrorResponse, "description": "If-Match wajib."},
}

_IfMatch = Annotated[
    str | None, Header(alias="If-Match", description="ETag untuk concurrency control.")
]
_IfNoneMatch = Annotated[
    str | None, Header(alias="If-None-Match", description="ETag klien untuk conditional GET.")
]


def _weak(tag: str) -> str:
    return tag[2:] if tag.startswith("W/") else tag


def _check_precondition(current: DetilTugasRead, if_match: str | None, required: bool) -> None:
    if if_match is None:
        if required:
            raise PreconditionRequiredError("Header If-Match wajib disertakan.")
        return
    if_match = if_match.strip()
    if if_match == "*":
        return
    current_etag = compute_etag(current)
    for candidate in if_match.split(","):
        candidate = candidate.strip()
        if candidate.startswith("W/"):
            continue
        if candidate == current_etag:
            return
    raise PreconditionFailedError("If-Match tidak cocok; resource telah berubah.")


def _matches_if_none_match(header: str, etag: str) -> bool:
    header = header.strip()
    if header == "*":
        return True
    target = _weak(etag)
    return any(_weak(c.strip()) == target for c in header.split(","))


def _pagination_links(
    response: Response, request: Request, total: int, limit: int, offset: int
) -> None:
    base = request.url.remove_query_params(["limit", "offset"])

    def url(off: int) -> str:
        return str(base.include_query_params(limit=limit, offset=off))

    links = [f'<{url(0)}>; rel="first"']
    if offset > 0:
        links.append(f'<{url(max(0, offset - limit))}>; rel="prev"')
    if offset + limit < total:
        links.append(f'<{url(offset + limit)}>; rel="next"')
    if total > 0 and limit > 0:
        links.append(f'<{url(((total - 1) // limit) * limit)}>; rel="last"')
    response.headers["Link"] = ", ".join(links)


@router.get(
    "",
    response_model=Page[DetilTugasRead],
    summary="Daftar detil tugas",
    operation_id="detil_tugas_list",
)
def list_detil_tugas(
    request: Request,
    response: Response,
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[DetilTugasService, Depends(get_detil_tugas_service)],
) -> Page[DetilTugasRead]:
    items, total = service.list(limit=page.limit, offset=page.offset)
    _pagination_links(response, request, total, page.limit, page.offset)
    return Page[DetilTugasRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=DetilTugasRead,
    status_code=status.HTTP_201_CREATED,
    summary="Buat detil tugas",
    operation_id="detil_tugas_create",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        404: {"model": ErrorResponse, "description": "TugasPokok induk tidak ditemukan."},
    },
)
def create_detil_tugas(
    payload: Annotated[
        DetilTugasCreate,
        Body(
            openapi_examples={
                "evaluasi_kinerja": {
                    "summary": "Mengevaluasi Kinerja Karyawan",
                    "value": {
                        "nama": "Mengevaluasi Kinerja Karyawan",
                        "tugas_pokok_id": "tp_a1b2c3d4",
                    },
                },
            }
        ),
    ],
    service: Annotated[DetilTugasService, Depends(get_detil_tugas_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> DetilTugasRead:
    cached = idem.cached()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        item = DetilTugasRead.model_validate(cached)
        response.headers["ETag"] = compute_etag(item)
        return item
    if not idem.reserve():
        raise ConflictError("Permintaan dengan Idempotency-Key ini sedang diproses.")
    try:
        item = service.create(payload)
    except Exception:
        idem.release()
        raise
    idem.remember(item)
    response.headers["ETag"] = compute_etag(item)
    return item


@router.post(
    "/search",
    response_model=Page[DetilTugasRead],
    summary="Cari detil tugas (domain ala Odoo)",
    operation_id="detil_tugas_search",
    responses={422: {"model": ErrorResponse, "description": "Domain/field tidak valid."}},
)
def search_detil_tugas(
    req: SearchRequest,
    service: Annotated[DetilTugasService, Depends(get_detil_tugas_service)],
) -> Page[DetilTugasRead]:
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[DetilTugasRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{dt_id}",
    response_model=DetilTugasRead,
    summary="Ambil detil tugas",
    operation_id="detil_tugas_get",
    responses={**_NOT_FOUND, 304: {"description": "Not Modified."}},
)
def get_detil_tugas(
    dt_id: Annotated[str, Path(description="ID detil tugas.")],
    service: Annotated[DetilTugasService, Depends(get_detil_tugas_service)],
    response: Response,
    if_none_match: _IfNoneMatch = None,
) -> DetilTugasRead | Response:
    item = service.get(dt_id)
    etag = compute_etag(item)
    if if_none_match is not None and _matches_if_none_match(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return item


@router.patch(
    "/{dt_id}",
    response_model=DetilTugasRead,
    summary="Perbarui detil tugas",
    operation_id="detil_tugas_update",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND, **_PRECONDITION},
)
def update_detil_tugas(
    dt_id: Annotated[str, Path(description="ID detil tugas.")],
    payload: DetilTugasUpdate,
    service: Annotated[DetilTugasService, Depends(get_detil_tugas_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: _IfMatch = None,
) -> DetilTugasRead:
    current = service.get(dt_id)
    _check_precondition(current, if_match, settings.require_if_match)
    updated = service.update(dt_id, payload)
    response.headers["ETag"] = compute_etag(updated)
    return updated


@router.delete(
    "/{dt_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus detil tugas",
    operation_id="detil_tugas_delete",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def delete_detil_tugas(
    dt_id: Annotated[str, Path(description="ID detil tugas.")],
    service: Annotated[DetilTugasService, Depends(get_detil_tugas_service)],
) -> Response:
    service.delete(dt_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
