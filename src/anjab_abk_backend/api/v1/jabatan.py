"""Endpoint resource `jabatan`: CRUD + search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Path, Request, Response, status

from ...anjab.schemas.jabatan import JabatanCreate, JabatanRead, JabatanUpdate
from ...anjab.services.jabatan import JabatanService
from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_current_principal,
    get_jabatan_service,
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
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Jabatan tidak ditemukan."}}
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


def _check_precondition(current: JabatanRead, if_match: str | None, required: bool) -> None:
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
    response_model=Page[JabatanRead],
    summary="Daftar jabatan",
    operation_id="jabatan_list",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE},
)
def list_jabatan(
    request: Request,
    response: Response,
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[JabatanService, Depends(get_jabatan_service)],
) -> Page[JabatanRead]:
    items, total = service.list(limit=page.limit, offset=page.offset)
    _pagination_links(response, request, total, page.limit, page.offset)
    return Page[JabatanRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=JabatanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Buat jabatan",
    operation_id="jabatan_create",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        409: {"model": ErrorResponse, "description": "Kode jabatan sudah ada."},
    },
)
def create_jabatan(
    payload: Annotated[
        JabatanCreate,
        Body(
            openapi_examples={
                "kepsek": {
                    "summary": "Kepala Sekolah",
                    "value": {
                        "kode": "KEPSEK",
                        "nama": "Kepala Sekolah",
                        "jenis": "struktural",
                        "deskripsi": "Pimpinan tertinggi satuan pendidikan.",
                    },
                },
                "guru_mtk": {
                    "summary": "Guru Matematika",
                    "value": {
                        "kode": "GURU-MTK",
                        "nama": "Guru Mata Pelajaran Matematika",
                        "jenis": "fungsional",
                    },
                },
            }
        ),
    ],
    service: Annotated[JabatanService, Depends(get_jabatan_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> JabatanRead:
    cached = idem.cached()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        item = JabatanRead.model_validate(cached)
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
    response_model=Page[JabatanRead],
    summary="Cari jabatan (domain ala Odoo)",
    operation_id="jabatan_search",
    dependencies=READ_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_jabatan(
    req: SearchRequest,
    service: Annotated[JabatanService, Depends(get_jabatan_service)],
) -> Page[JabatanRead]:
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[JabatanRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{jabatan_id}",
    response_model=JabatanRead,
    summary="Ambil jabatan",
    operation_id="jabatan_get",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND, 304: {"description": "Not Modified."}},
)
def get_jabatan(
    jabatan_id: Annotated[str, Path(description="ID jabatan.")],
    service: Annotated[JabatanService, Depends(get_jabatan_service)],
    response: Response,
    if_none_match: _IfNoneMatch = None,
) -> JabatanRead | Response:
    item = service.get(jabatan_id)
    etag = compute_etag(item)
    if if_none_match is not None and _matches_if_none_match(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return item


@router.patch(
    "/{jabatan_id}",
    response_model=JabatanRead,
    summary="Perbarui jabatan",
    operation_id="jabatan_update",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND, **_PRECONDITION},
)
def update_jabatan(
    jabatan_id: Annotated[str, Path(description="ID jabatan.")],
    payload: JabatanUpdate,
    service: Annotated[JabatanService, Depends(get_jabatan_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: _IfMatch = None,
) -> JabatanRead:
    current = service.get(jabatan_id)
    _check_precondition(current, if_match, settings.require_if_match)
    updated = service.update(jabatan_id, payload)
    response.headers["ETag"] = compute_etag(updated)
    return updated


@router.delete(
    "/{jabatan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus jabatan",
    operation_id="jabatan_delete",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def delete_jabatan(
    jabatan_id: Annotated[str, Path(description="ID jabatan.")],
    service: Annotated[JabatanService, Depends(get_jabatan_service)],
) -> Response:
    service.delete(jabatan_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
