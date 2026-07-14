"""Endpoint resource `sekolah`: CRUD + search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Path, Request, Response, status

from ...config import Settings, get_settings
from ...core.schemas.sekolah import SekolahCreate, SekolahRead, SekolahUpdate
from ...core.services.sekolah import SekolahService
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_current_principal,
    get_sekolah_service,
    idempotency,
    pagination_params,
    rate_limit,
)
from ...errors import ConflictError, PreconditionFailedError, PreconditionRequiredError
from ...etag import compute_etag
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Sekolah tidak ditemukan."}}
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


def _check_precondition(current: SekolahRead, if_match: str | None, required: bool) -> None:
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
    response_model=Page[SekolahRead],
    summary="Daftar sekolah",
    operation_id="sekolah_list",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE},
)
def list_sekolah(
    request: Request,
    response: Response,
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[SekolahService, Depends(get_sekolah_service)],
) -> Page[SekolahRead]:
    items, total = service.list(limit=page.limit, offset=page.offset)
    _pagination_links(response, request, total, page.limit, page.offset)
    return Page[SekolahRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=SekolahRead,
    status_code=status.HTTP_201_CREATED,
    summary="Buat sekolah",
    operation_id="sekolah_create",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        409: {"model": ErrorResponse, "description": "NPSN sudah terdaftar."},
    },
)
def create_sekolah(
    payload: Annotated[
        SekolahCreate,
        Body(
            openapi_examples={
                "sd": {
                    "summary": "SD Negeri",
                    "value": {
                        "nama": "SD Negeri 1 Bandung",
                        "npsn": "20201234",
                        "jenjang_pendidikan_id": "jp_a1b2c3d4",
                        "kota": "Bandung",
                        "provinsi": "Jawa Barat",
                    },
                },
            }
        ),
    ],
    service: Annotated[SekolahService, Depends(get_sekolah_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> SekolahRead:
    cached = idem.cached()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        item = SekolahRead.model_validate(cached)
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
    response_model=Page[SekolahRead],
    summary="Cari sekolah (domain ala Odoo)",
    operation_id="sekolah_search",
    dependencies=READ_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_sekolah(
    req: SearchRequest,
    service: Annotated[SekolahService, Depends(get_sekolah_service)],
) -> Page[SekolahRead]:
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[SekolahRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{sekolah_id}",
    response_model=SekolahRead,
    summary="Ambil sekolah",
    operation_id="sekolah_get",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND, 304: {"description": "Not Modified."}},
)
def get_sekolah(
    sekolah_id: Annotated[str, Path(description="ID sekolah.")],
    service: Annotated[SekolahService, Depends(get_sekolah_service)],
    response: Response,
    if_none_match: _IfNoneMatch = None,
) -> SekolahRead | Response:
    item = service.get(sekolah_id)
    etag = compute_etag(item)
    if if_none_match is not None and _matches_if_none_match(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return item


@router.patch(
    "/{sekolah_id}",
    response_model=SekolahRead,
    summary="Perbarui sekolah",
    operation_id="sekolah_update",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND, **_PRECONDITION},
)
def update_sekolah(
    sekolah_id: Annotated[str, Path(description="ID sekolah.")],
    payload: SekolahUpdate,
    service: Annotated[SekolahService, Depends(get_sekolah_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: _IfMatch = None,
) -> SekolahRead:
    current = service.get(sekolah_id)
    _check_precondition(current, if_match, settings.require_if_match)
    updated = service.update(sekolah_id, payload)
    response.headers["ETag"] = compute_etag(updated)
    return updated


@router.delete(
    "/{sekolah_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus sekolah",
    operation_id="sekolah_delete",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def delete_sekolah(
    sekolah_id: Annotated[str, Path(description="ID sekolah.")],
    service: Annotated[SekolahService, Depends(get_sekolah_service)],
) -> Response:
    service.delete(sekolah_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
