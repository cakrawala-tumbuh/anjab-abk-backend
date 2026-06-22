"""Endpoint resource `sme_panel`: CRUD + manajemen anggota."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Path, Request, Response, status

from ...anjab.schemas.sme_panel import (
    SMEPanelAnggotaAdd,
    SMEPanelCreate,
    SMEPanelRead,
    SMEPanelUpdate,
)
from ...anjab.services.sme_panel import SMEPanelService
from ...config import Settings, get_settings
from ...dependencies import (
    Idempotency,
    Pagination,
    get_current_principal,
    get_sme_panel_service,
    idempotency,
    pagination_params,
    rate_limit,
)
from ...errors import (
    ConflictError,
    PreconditionFailedError,
    PreconditionRequiredError,
    ValidationAppError,
)
from ...etag import compute_etag
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "SME panel tidak ditemukan."}}
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


def _check_precondition(current: SMEPanelRead, if_match: str | None, required: bool) -> None:
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
    response_model=Page[SMEPanelRead],
    summary="Daftar SME panel",
    operation_id="sme_panel_list",
)
def list_sme_panel(
    request: Request,
    response: Response,
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[SMEPanelService, Depends(get_sme_panel_service)],
) -> Page[SMEPanelRead]:
    items, total = service.list(limit=page.limit, offset=page.offset)
    _pagination_links(response, request, total, page.limit, page.offset)
    return Page[SMEPanelRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=SMEPanelRead,
    status_code=status.HTTP_201_CREATED,
    summary="Buat SME panel",
    operation_id="sme_panel_create",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        409: {"model": ErrorResponse, "description": "Panel untuk jabatan ini sudah ada."},
    },
)
def create_sme_panel(
    payload: Annotated[
        SMEPanelCreate,
        Body(
            openapi_examples={
                "kepsek": {
                    "summary": "Panel SME untuk Kepala Sekolah",
                    "value": {
                        "jabatan_id": "jbt_a1b2c3d4",
                        "aktif": True,
                    },
                },
            }
        ),
    ],
    service: Annotated[SMEPanelService, Depends(get_sme_panel_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> SMEPanelRead:
    cached = idem.cached()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        item = SMEPanelRead.model_validate(cached)
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
    response_model=Page[SMEPanelRead],
    summary="Cari SME panel (domain ala Odoo)",
    operation_id="sme_panel_search",
    responses={422: {"model": ErrorResponse, "description": "Domain/field tidak valid."}},
)
def search_sme_panel(
    req: SearchRequest,
    service: Annotated[SMEPanelService, Depends(get_sme_panel_service)],
) -> Page[SMEPanelRead]:
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[SMEPanelRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{panel_id}",
    response_model=SMEPanelRead,
    summary="Ambil SME panel",
    operation_id="sme_panel_get",
    responses={**_NOT_FOUND, 304: {"description": "Not Modified."}},
)
def get_sme_panel(
    panel_id: Annotated[str, Path(description="ID SME panel.")],
    service: Annotated[SMEPanelService, Depends(get_sme_panel_service)],
    response: Response,
    if_none_match: _IfNoneMatch = None,
) -> SMEPanelRead | Response:
    item = service.get(panel_id)
    etag = compute_etag(item)
    if if_none_match is not None and _matches_if_none_match(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return item


@router.patch(
    "/{panel_id}",
    response_model=SMEPanelRead,
    summary="Perbarui SME panel",
    operation_id="sme_panel_update",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_NOT_FOUND,
        **_PRECONDITION,
        422: {
            "model": ErrorResponse,
            "description": "Koordinator bukan anggota panel.",
        },
    },
)
def update_sme_panel(
    panel_id: Annotated[str, Path(description="ID SME panel.")],
    payload: SMEPanelUpdate,
    service: Annotated[SMEPanelService, Depends(get_sme_panel_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: _IfMatch = None,
) -> SMEPanelRead:
    current = service.get(panel_id)
    _check_precondition(current, if_match, settings.require_if_match)
    if "koordinator_id" in payload.model_fields_set and payload.koordinator_id is not None:
        if payload.koordinator_id not in current.partisipan_ids:
            raise ValidationAppError("Koordinator harus merupakan anggota panel SME ini.")
    updated = service.update(panel_id, payload)
    response.headers["ETag"] = compute_etag(updated)
    return updated


@router.delete(
    "/{panel_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus SME panel",
    operation_id="sme_panel_delete",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def delete_sme_panel(
    panel_id: Annotated[str, Path(description="ID SME panel.")],
    service: Annotated[SMEPanelService, Depends(get_sme_panel_service)],
) -> Response:
    service.delete(panel_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{panel_id}/anggota",
    response_model=SMEPanelRead,
    summary="Tambah anggota ke SME panel",
    operation_id="sme_panel_add_anggota",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_NOT_FOUND,
        409: {"model": ErrorResponse, "description": "Partisipan sudah anggota panel ini."},
    },
)
def add_anggota(
    panel_id: Annotated[str, Path(description="ID SME panel.")],
    payload: SMEPanelAnggotaAdd,
    service: Annotated[SMEPanelService, Depends(get_sme_panel_service)],
    response: Response,
) -> SMEPanelRead:
    updated = service.add_anggota(panel_id, payload.partisipan_id)
    response.headers["ETag"] = compute_etag(updated)
    return updated


@router.delete(
    "/{panel_id}/anggota/{partisipan_id}",
    response_model=SMEPanelRead,
    summary="Hapus anggota dari SME panel",
    operation_id="sme_panel_remove_anggota",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def remove_anggota(
    panel_id: Annotated[str, Path(description="ID SME panel.")],
    partisipan_id: Annotated[str, Path(description="ID partisipan yang akan dihapus dari panel.")],
    service: Annotated[SMEPanelService, Depends(get_sme_panel_service)],
    response: Response,
) -> SMEPanelRead:
    updated = service.remove_anggota(panel_id, partisipan_id)
    response.headers["ETag"] = compute_etag(updated)
    return updated
