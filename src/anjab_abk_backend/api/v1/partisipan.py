"""Endpoint resource `partisipan`: CRUD + search."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, Path, Request, Response, status

from ...config import Settings, get_settings
from ...core.schemas.partisipan import PartisipanCreate, PartisipanRead, PartisipanUpdate
from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_authentik_provisioner,
    get_current_principal,
    get_partisipan_service,
    idempotency,
    pagination_params,
    rate_limit,
)
from ...errors import (
    ConflictError,
    NotFoundError,
    PreconditionFailedError,
    PreconditionRequiredError,
)
from ...etag import compute_etag
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ...security import Principal
from ...services.authentik_provisioner import AuthentikProvisioner

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Partisipan tidak ditemukan."}}
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


def _check_precondition(current: PartisipanRead, if_match: str | None, required: bool) -> None:
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
    response_model=Page[PartisipanRead],
    summary="Daftar partisipan",
    operation_id="partisipan_list",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE},
)
def list_partisipan(
    request: Request,
    response: Response,
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> Page[PartisipanRead]:
    items, total = service.list(limit=page.limit, offset=page.offset)
    _pagination_links(response, request, total, page.limit, page.offset)
    return Page[PartisipanRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=PartisipanRead,
    status_code=status.HTTP_201_CREATED,
    summary="Buat partisipan",
    operation_id="partisipan_create",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE},
)
def create_partisipan(
    payload: Annotated[
        PartisipanCreate,
        Body(
            openapi_examples={
                "guru": {
                    "summary": "Guru matematika dengan jabatan tambahan",
                    "value": {
                        "nama": "Siti Rahayu, S.Pd.",
                        "email": "siti.rahayu@sekolah.id",
                        "sekolah_id": "skl_a1b2c3d4",
                        "jabatan_utama_id": "jbt_a1b2c3d4",
                        "jabatan_tambahan_ids": ["jbt_b2c3d4e5"],
                        "masa_kerja_tahun": 5,
                        "masa_kerja_bulan": 3,
                        "mata_pelajaran_utama_id": "mp_a1b2c3d4",
                    },
                },
                "staf": {
                    "summary": "Staf tata usaha tanpa mata pelajaran",
                    "value": {
                        "nama": "Budi Santoso",
                        "email": "budi.santoso@sekolah.id",
                        "sekolah_id": "skl_a1b2c3d4",
                        "jabatan_utama_id": "jbt_c3d4e5f6",
                        "jabatan_tambahan_ids": [],
                        "masa_kerja_tahun": 2,
                        "masa_kerja_bulan": 0,
                    },
                },
            }
        ),
    ],
    service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    provisioner: Annotated[AuthentikProvisioner, Depends(get_authentik_provisioner)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> PartisipanRead:
    cached = idem.cached()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        item = PartisipanRead.model_validate(cached)
        response.headers["ETag"] = compute_etag(item)
        return item
    if not idem.reserve():
        raise ConflictError("Permintaan dengan Idempotency-Key ini sedang diproses.")
    try:
        authentik_user_id = provisioner.create_partisipan_user(
            nama=payload.nama, email=payload.email
        )
        item = service.create(payload, authentik_user_id=authentik_user_id)
    except Exception:
        idem.release()
        raise
    idem.remember(item)
    response.headers["ETag"] = compute_etag(item)
    return item


@router.post(
    "/search",
    response_model=Page[PartisipanRead],
    summary="Cari partisipan (domain ala Odoo)",
    operation_id="partisipan_search",
    dependencies=READ_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_partisipan(
    req: SearchRequest,
    service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> Page[PartisipanRead]:
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[PartisipanRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/saya",
    response_model=PartisipanRead,
    summary="Partisipan saat ini (berdasarkan token Bearer)",
    operation_id="partisipan_saya",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_NOT_FOUND},
)
def get_partisipan_saya(
    principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> PartisipanRead:
    par = service.get_by_subject(principal.subject)
    if par is None:
        raise NotFoundError("Partisipan tidak ditemukan untuk pengguna ini.")
    return par


@router.get(
    "/{partisipan_id}",
    response_model=PartisipanRead,
    summary="Ambil partisipan",
    operation_id="partisipan_get",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND, 304: {"description": "Not Modified."}},
)
def get_partisipan(
    partisipan_id: Annotated[str, Path(description="ID partisipan.")],
    service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    response: Response,
    if_none_match: _IfNoneMatch = None,
) -> PartisipanRead | Response:
    item = service.get(partisipan_id)
    etag = compute_etag(item)
    if if_none_match is not None and _matches_if_none_match(if_none_match, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    response.headers["ETag"] = etag
    return item


@router.patch(
    "/{partisipan_id}",
    response_model=PartisipanRead,
    summary="Perbarui partisipan",
    operation_id="partisipan_update",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND, **_PRECONDITION},
)
def update_partisipan(
    partisipan_id: Annotated[str, Path(description="ID partisipan.")],
    payload: PartisipanUpdate,
    service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: _IfMatch = None,
) -> PartisipanRead:
    current = service.get(partisipan_id)
    _check_precondition(current, if_match, settings.require_if_match)
    updated = service.update(partisipan_id, payload)
    response.headers["ETag"] = compute_etag(updated)
    return updated


@router.delete(
    "/{partisipan_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus partisipan",
    operation_id="partisipan_delete",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE, **_NOT_FOUND},
)
def delete_partisipan(
    partisipan_id: Annotated[str, Path(description="ID partisipan.")],
    service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> Response:
    service.delete(partisipan_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
