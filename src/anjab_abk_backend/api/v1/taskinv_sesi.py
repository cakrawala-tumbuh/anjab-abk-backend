"""Endpoint resource `TiSesi`: CRUD + transisi status 3 tahap."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Path, Query, Response, status

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    Idempotency,
    Pagination,
    authorize_sesi_access,
    get_current_principal,
    get_partisipan_service,
    get_ti_catalog_service,
    get_ti_responden_service,
    get_ti_seleksi_service,
    get_ti_sesi_service,
    get_ti_tahap2_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_admin,
)
from ...errors import ConflictError, ValidationAppError
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ...security import Principal
from ...taskinv.schemas.sesi import TiSesiCreate, TiSesiRead, TiSesiUpdate
from ...taskinv.services.catalog import TiCatalogService
from ...taskinv.services.responden import TiRespondenService
from ...taskinv.services.seleksi import TiSeleksiService
from ...taskinv.services.sesi import TiSesiService
from ...taskinv.services.tahap2 import TiTahap2Service

router = APIRouter()

logger = logging.getLogger("anjab_abk_backend.api.v1.taskinv_sesi")

_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_NOT_FOUND = {404: {"model": ErrorResponse, "description": "Sesi Task Inventory tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan admin."}}
_FORBIDDEN_PESERTA = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau peserta sesi."}
}


@router.get(
    "",
    response_model=Page[TiSesiRead],
    summary="Daftar sesi Task Inventory (admin)",
    operation_id="taskinv_sesi_list",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_sesi(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
) -> Page[TiSesiRead]:
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[TiSesiRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=TiSesiRead,
    status_code=status.HTTP_201_CREATED,
    summary="Buat sesi Task Inventory (admin)",
    operation_id="taskinv_sesi_create",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {"model": ErrorResponse, "description": "Sesi untuk jabatan+periode sudah ada."},
    },
)
def create_sesi(
    payload: Annotated[
        TiSesiCreate,
        Body(
            openapi_examples={
                "contoh": {
                    "summary": "Sesi TI Kepala Sekolah",
                    "value": {
                        "jabatan_id": "jbt_a1b2c3d4",
                        "periode": "2026-06",
                        "min_responden": 3,
                        "max_responden": 10,
                    },
                }
            }
        ),
    ],
    service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    catalog: Annotated[TiCatalogService, Depends(get_ti_catalog_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> TiSesiRead:
    if not catalog.valid_kodes_for_jabatan(payload.jabatan_id):
        raise ValidationAppError(f"Tidak ada task catalog untuk jabatan '{payload.jabatan_id}'.")
    cached = idem.cached()
    if cached is not None:
        response.status_code = status.HTTP_200_OK
        return TiSesiRead.model_validate(cached)
    if not idem.reserve():
        raise ConflictError("Permintaan dengan Idempotency-Key ini sedang diproses.")
    try:
        item = service.create(payload)
    except Exception:
        idem.release()
        raise
    idem.remember(item)
    return item


@router.post(
    "/search",
    response_model=Page[TiSesiRead],
    summary="Cari sesi Task Inventory (domain ala Odoo) (admin)",
    operation_id="taskinv_sesi_search",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_sesi(
    req: SearchRequest,
    service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
) -> Page[TiSesiRead]:
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[TiSesiRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{sesi_id}",
    response_model=TiSesiRead,
    summary="Ambil sesi Task Inventory (admin atau peserta sesi)",
    operation_id="taskinv_sesi_get",
    responses={**_AUTH, **_FORBIDDEN_PESERTA, **_NOT_FOUND},
)
def get_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
) -> TiSesiRead:
    sesi = service.get(sesi_id)
    authorize_sesi_access(principal, sesi, par_service, rsp_service)
    return sesi


@router.patch(
    "/{sesi_id}",
    response_model=TiSesiRead,
    summary="Perbarui sesi Task Inventory (hanya saat DRAFT) (admin)",
    operation_id="taskinv_sesi_update",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND},
)
def update_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    payload: TiSesiUpdate,
    service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
) -> TiSesiRead:
    return service.update(sesi_id, payload)


@router.delete(
    "/{sesi_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus sesi Task Inventory (DRAFT bebas; status lain wajib paksa=true)",
    operation_id="taskinv_sesi_delete",
    dependencies=[Depends(rate_limit)],
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND,
        422: {
            "model": ErrorResponse,
            "description": "Sesi bukan DRAFT dan paksa tidak di-set.",
        },
    },
)
def delete_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    principal: Annotated[Principal, Depends(require_admin)],
    paksa: Annotated[
        bool,
        Query(
            description=(
                "Paksa hapus sesi non-DRAFT beserta SELURUH responden & jawabannya (permanen)."
            )
        ),
    ] = False,
) -> Response:
    if paksa:
        logger.warning(
            "force_delete_sesi",
            extra={"modul": "taskinv", "sesi_id": sesi_id, "actor": principal.subject},
        )
    service.delete(sesi_id, paksa=paksa)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{sesi_id}/mulai-tahap1",
    response_model=TiSesiRead,
    summary="Mulai Tahap 1 — Seleksi Relevansi (DRAFT → TAHAP1) (admin)",
    operation_id="taskinv_sesi_mulai_tahap1",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND},
)
def mulai_tahap1(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
) -> TiSesiRead:
    return service.transition(sesi_id, "TAHAP1")


@router.post(
    "/{sesi_id}/mulai-tahap2",
    response_model=TiSesiRead,
    summary="Mulai Tahap 2 — Review Koordinator (TAHAP1 → TAHAP2) (admin)",
    operation_id="taskinv_sesi_mulai_tahap2",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND,
        422: {
            "model": ErrorResponse,
            "description": "Belum ada responden yang submit Tahap 1.",
        },
    },
)
def mulai_tahap2(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    paksa: Annotated[
        bool,
        Query(description="Paksa lanjut walau belum semua partisipan submit Tahap 1."),
    ] = False,
) -> TiSesiRead:
    sesi = service.get(sesi_id)
    if sesi.status != "TAHAP1":
        raise ValidationAppError(
            f"Tahap 2 hanya dapat dimulai dari TAHAP1 (saat ini: {sesi.status})."
        )
    total = rsp_service.count_by_sesi(sesi_id)
    submitted = rsp_service.count_tahap1_submitted(sesi_id)
    if submitted == 0:
        raise ValidationAppError("Belum ada partisipan yang submit Tahap 1.")
    if submitted < total and not paksa:
        raise ValidationAppError(
            f"Baru {submitted} dari {total} partisipan submit Tahap 1."
            " Gunakan paksa=true untuk tetap melanjutkan."
        )
    return service.transition(sesi_id, "TAHAP2")


@router.post(
    "/{sesi_id}/mulai-tahap3",
    response_model=TiSesiRead,
    summary="Mulai Tahap 3 — Detailing (TAHAP2 → TAHAP3), bekukan task relevan (admin)",
    operation_id="taskinv_sesi_mulai_tahap3",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND,
        422: {
            "model": ErrorResponse,
            "description": "Belum semua task diputuskan koordinator / tidak ada task relevan.",
        },
    },
)
def mulai_tahap3(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    seleksi_service: Annotated[TiSeleksiService, Depends(get_ti_seleksi_service)],
    tahap2_service: Annotated[TiTahap2Service, Depends(get_ti_tahap2_service)],
    paksa: Annotated[
        bool,
        Query(
            description=(
                "Paksa lanjut walau masih ada task partial" " yang belum diputuskan koordinator."
            )
        ),
    ] = False,
) -> TiSesiRead:
    sesi = service.get(sesi_id)
    if sesi.status != "TAHAP2":
        raise ValidationAppError(
            f"Tahap 3 hanya dapat dimulai dari TAHAP2 (saat ini: {sesi.status})."
        )
    n_submitted = rsp_service.count_tahap1_submitted(sesi_id)
    unanimous = seleksi_service.unanimous_terpilih(sesi_id, n_submitted)
    partial = seleksi_service.partial_terpilih(sesi_id, n_submitted)
    counts = seleksi_service.count_relevan_per_task(sesi_id)

    if partial:
        review = tahap2_service.get_review(sesi_id, partial, counts, n_submitted)
        if review.jumlah_belum_diputuskan > 0 and not paksa:
            raise ValidationAppError(
                f"Masih ada {review.jumlah_belum_diputuskan} task"
                " yang belum diputuskan koordinator."
                " Gunakan paksa=true untuk tetap melanjutkan"
                " (task belum diputuskan akan diabaikan)."
            )

    approved = tahap2_service.get_approved_kodes(sesi_id)
    final_kodes = sorted(set(unanimous) | set(approved))
    return service.freeze_task_terpilih(sesi_id, final_kodes)


@router.post(
    "/{sesi_id}/tutup",
    response_model=TiSesiRead,
    summary="Tutup sesi (TAHAP3 → CLOSED) (admin)",
    operation_id="taskinv_sesi_tutup",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND},
)
def tutup_sesi(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
) -> TiSesiRead:
    return service.transition(sesi_id, "CLOSED")
