"""Endpoint resource `uraian-tugas`: CRUD + search (master data catalog TI)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Path, Request, Response, status

from ...config import Settings, get_settings
from ...dependencies import (
    Idempotency,
    Pagination,
    get_current_principal,
    get_uraian_tugas_service,
    idempotency,
    pagination_params,
    rate_limit,
)
from ...errors import ConflictError, PreconditionFailedError, PreconditionRequiredError
from ...etag import compute_etag
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ...taskinv.schemas.uraian_tugas import UraianTugasCreate, UraianTugasRead, UraianTugasUpdate
from ...taskinv.services.uraian_tugas import UraianTugasService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "UraianTugas tidak ditemukan."}}
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


def _check_precondition(current: UraianTugasRead, if_match: str | None, required: bool) -> None:
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
    response_model=Page[UraianTugasRead],
    summary="Daftar uraian tugas",
    operation_id="uraian_tugas_list",
)
def list_uraian_tugas(
    request: Request,
    response: Response,
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[UraianTugasService, Depends(get_uraian_tugas_service)],
) -> Page[UraianTugasRead]:
    items, total = service.list(limit=page.limit, offset=page.offset)
    _pagination_links(response, request, total, page.limit, page.offset)
    return Page[UraianTugasRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=UraianTugasRead,
    status_code=status.HTTP_201_CREATED,
    summary="Buat uraian tugas",
    operation_id="uraian_tugas_create",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        409: {"model": ErrorResponse, "description": "Kode uraian tugas sudah ada."},
    },
)
def create_uraian_tugas(
    payload: Annotated[
        UraianTugasCreate,
        Body(
            openapi_examples={
                "evaluasi_karyawan": {
                    "summary": "Menyusun evaluasi karyawan",
                    "value": {
                        "kode": "TIf0b59714",
                        "uraian": "Menyusun evaluasi karyawan",
                        "unit": "TK",
                        "kategori_jabatan": "Kepala Sekolah",
                        "urutan": 1,
                        "detil_tugas_id": "dt_a1b2c3d4",
                        "tugas_pokok_id": "tp_a1b2c3d4",
                    },
                },
            }
        ),
    ],
    service: Annotated[UraianTugasService, Depends(get_uraian_tugas_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> UraianTugasRead:
    cached = idem.cached()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        item = UraianTugasRead.model_validate(cached)
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
    response_model=Page[UraianTugasRead],
    summary="Cari uraian tugas (domain ala Odoo)",
    operation_id="uraian_tugas_search",
    responses={422: {"model": ErrorResponse, "description": "Domain/field tidak valid."}},
)
def search_uraian_tugas(
    req: SearchRequest,
    service: Annotated[UraianTugasService, Depends(get_uraian_tugas_service)],
) -> Page[UraianTugasRead]:
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[UraianTugasRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{ut_id}",
    response_model=UraianTugasRead,
    summary="Ambil uraian tugas",
    operation_id="uraian_tugas_get",
    responses={**_NOT_FOUND, 304: {"description": "Not Modified."}},
)
def get_uraian_tugas(
    ut_id: Annotated[str, Path(description="ID uraian tugas.")],
    service: Annotated[UraianTugasService, Depends(get_uraian_tugas_service)],
    response: Response,
    if_none_match: _IfNoneMatch = None,
) -> UraianTugasRead | Response:
    item = service.get(ut_id)
    etag = compute_etag(item)
    if if_none_match is not None and _matches_if_none_match(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return item


@router.patch(
    "/{ut_id}",
    response_model=UraianTugasRead,
    summary="Perbarui uraian tugas",
    operation_id="uraian_tugas_update",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND, **_PRECONDITION},
)
def update_uraian_tugas(
    ut_id: Annotated[str, Path(description="ID uraian tugas.")],
    payload: UraianTugasUpdate,
    service: Annotated[UraianTugasService, Depends(get_uraian_tugas_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: _IfMatch = None,
) -> UraianTugasRead:
    current = service.get(ut_id)
    _check_precondition(current, if_match, settings.require_if_match)
    updated = service.update(ut_id, payload)
    response.headers["ETag"] = compute_etag(updated)
    return updated


@router.delete(
    "/{ut_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus uraian tugas",
    operation_id="uraian_tugas_delete",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def delete_uraian_tugas(
    ut_id: Annotated[str, Path(description="ID uraian tugas.")],
    service: Annotated[UraianTugasService, Depends(get_uraian_tugas_service)],
) -> Response:
    service.delete(ut_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
