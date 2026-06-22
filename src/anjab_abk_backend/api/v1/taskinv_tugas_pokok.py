"""Endpoint resource `tugas-pokok`: CRUD + search (master data catalog TI)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Path, Request, Response, status

from ...config import Settings, get_settings
from ...dependencies import (
    Idempotency,
    Pagination,
    get_current_principal,
    get_tugas_pokok_service,
    idempotency,
    pagination_params,
    rate_limit,
)
from ...errors import ConflictError, PreconditionFailedError, PreconditionRequiredError
from ...etag import compute_etag
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ...taskinv.schemas.tugas_pokok import TugasPokokCreate, TugasPokokRead, TugasPokokUpdate
from ...taskinv.services.tugas_pokok import TugasPokokService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "TugasPokok tidak ditemukan."}}
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


def _check_precondition(current: TugasPokokRead, if_match: str | None, required: bool) -> None:
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
    response_model=Page[TugasPokokRead],
    summary="Daftar tugas pokok",
    operation_id="tugas_pokok_list",
)
def list_tugas_pokok(
    request: Request,
    response: Response,
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[TugasPokokService, Depends(get_tugas_pokok_service)],
) -> Page[TugasPokokRead]:
    items, total = service.list(limit=page.limit, offset=page.offset)
    _pagination_links(response, request, total, page.limit, page.offset)
    return Page[TugasPokokRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=TugasPokokRead,
    status_code=status.HTTP_201_CREATED,
    summary="Buat tugas pokok",
    operation_id="tugas_pokok_create",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        409: {"model": ErrorResponse, "description": "Nama tugas pokok sudah ada."},
    },
)
def create_tugas_pokok(
    payload: Annotated[
        TugasPokokCreate,
        Body(
            openapi_examples={
                "pengelolaan_sdm": {
                    "summary": "Pengelolaan SDM",
                    "value": {"jabatan_id": "jbt_a1b2c3d4", "nama": "Pengelolaan SDM"},
                },
            }
        ),
    ],
    service: Annotated[TugasPokokService, Depends(get_tugas_pokok_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> TugasPokokRead:
    cached = idem.cached()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        item = TugasPokokRead.model_validate(cached)
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
    response_model=Page[TugasPokokRead],
    summary="Cari tugas pokok (domain ala Odoo)",
    operation_id="tugas_pokok_search",
    responses={422: {"model": ErrorResponse, "description": "Domain/field tidak valid."}},
)
def search_tugas_pokok(
    req: SearchRequest,
    service: Annotated[TugasPokokService, Depends(get_tugas_pokok_service)],
) -> Page[TugasPokokRead]:
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[TugasPokokRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{tp_id}",
    response_model=TugasPokokRead,
    summary="Ambil tugas pokok",
    operation_id="tugas_pokok_get",
    responses={**_NOT_FOUND, 304: {"description": "Not Modified."}},
)
def get_tugas_pokok(
    tp_id: Annotated[str, Path(description="ID tugas pokok.")],
    service: Annotated[TugasPokokService, Depends(get_tugas_pokok_service)],
    response: Response,
    if_none_match: _IfNoneMatch = None,
) -> TugasPokokRead | Response:
    item = service.get(tp_id)
    etag = compute_etag(item)
    if if_none_match is not None and _matches_if_none_match(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return item


@router.patch(
    "/{tp_id}",
    response_model=TugasPokokRead,
    summary="Perbarui tugas pokok",
    operation_id="tugas_pokok_update",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND, **_PRECONDITION},
)
def update_tugas_pokok(
    tp_id: Annotated[str, Path(description="ID tugas pokok.")],
    payload: TugasPokokUpdate,
    service: Annotated[TugasPokokService, Depends(get_tugas_pokok_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: _IfMatch = None,
) -> TugasPokokRead:
    current = service.get(tp_id)
    _check_precondition(current, if_match, settings.require_if_match)
    updated = service.update(tp_id, payload)
    response.headers["ETag"] = compute_etag(updated)
    return updated


@router.delete(
    "/{tp_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus tugas pokok",
    operation_id="tugas_pokok_delete",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def delete_tugas_pokok(
    tp_id: Annotated[str, Path(description="ID tugas pokok.")],
    service: Annotated[TugasPokokService, Depends(get_tugas_pokok_service)],
) -> Response:
    service.delete(tp_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
