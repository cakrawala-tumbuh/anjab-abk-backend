"""Endpoint review koordinator Tahap 2 Task Inventory."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    READ_GUARDS,
    authorize_sesi_access,
    get_current_principal,
    get_partisipan_service,
    get_ti_catalog_service,
    get_ti_responden_service,
    get_ti_seleksi_service,
    get_ti_sesi_service,
    get_ti_tahap2_service,
    get_ti_usulan_service,
    rate_limit,
)
from ...errors import ForbiddenError, ValidationAppError
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...taskinv.schemas.tahap2 import TiTahap2ReviewRead, TiTahap2Submit, TiUsulanReviewRead
from ...taskinv.schemas.usulan import TiUsulanRead
from ...taskinv.services.catalog import TiCatalogService
from ...taskinv.services.responden import TiRespondenService
from ...taskinv.services.seleksi import TiSeleksiService
from ...taskinv.services.sesi import TiSesiService
from ...taskinv.services.tahap2 import TiTahap2Service
from ...taskinv.services.usulan import TiUsulanService

router = APIRouter()


def _to_usulan_review(usulan: TiUsulanRead, rsp_service: TiRespondenService) -> TiUsulanReviewRead:
    """Proyeksikan `TiUsulanRead` ke `TiUsulanReviewRead`, menambah `responden_nama`.

    `responden_id` selalu valid saat proyeksi ini dipanggil (FK `ON DELETE CASCADE`
    ke `ti_responden` — usulan tidak mungkin outlive respondennya), jadi `.get()`
    dipanggil langsung tanpa fallback.
    """
    responden = rsp_service.get(usulan.responden_id)
    return TiUsulanReviewRead(
        usulan_id=usulan.id,
        responden_id=usulan.responden_id,
        responden_nama=responden.nama,
        tugas_pokok=usulan.tugas_pokok,
        detil_tugas=usulan.detil_tugas,
        uraian=usulan.uraian,
        disetujui=usulan.disetujui,
    )


_RATE_GUARD = [Depends(rate_limit)]
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN_PESERTA = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau peserta sesi."}
}


@router.get(
    "/{sesi_id}/tahap2",
    response_model=TiTahap2ReviewRead,
    summary="Lihat task yang perlu diputuskan koordinator di Tahap 2 (admin atau peserta sesi)",
    operation_id="taskinv_tahap2_get",
    dependencies=READ_GUARDS,
    responses={
        **_RATE,
        **_AUTH,
        **_FORBIDDEN_PESERTA,
        **_NOT_FOUND_SESI,
        422: {"model": ErrorResponse},
    },
)
def get_tahap2_review(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    seleksi_service: Annotated[TiSeleksiService, Depends(get_ti_seleksi_service)],
    tahap2_service: Annotated[TiTahap2Service, Depends(get_ti_tahap2_service)],
    usulan_service: Annotated[TiUsulanService, Depends(get_ti_usulan_service)],
) -> TiTahap2ReviewRead:
    sesi = sesi_service.get(sesi_id)
    authorize_sesi_access(principal, sesi, par_service, rsp_service)
    if sesi.status not in ("TAHAP2", "TAHAP3", "CLOSED", "ANALYZED"):
        raise ValidationAppError(
            f"Review Tahap 2 hanya tersedia setelah TAHAP2 (saat ini: {sesi.status})."
        )
    n_submitted = rsp_service.count_tahap1_submitted(sesi_id)
    partial = seleksi_service.partial_terpilih(sesi_id, n_submitted)
    counts = seleksi_service.count_relevan_per_task(sesi_id)
    usulan = [_to_usulan_review(u, rsp_service) for u in usulan_service.list_by_sesi(sesi_id)]
    return tahap2_service.get_review(sesi_id, partial, counts, n_submitted, usulan)


_FORBIDDEN_SESI = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau koordinator sesi."}
}


@router.post(
    "/{sesi_id}/tahap2",
    response_model=TiTahap2ReviewRead,
    summary="Submit keputusan koordinator untuk task-task Tahap 2",
    operation_id="taskinv_tahap2_submit",
    dependencies=_RATE_GUARD,
    responses={
        **_AUTH,
        **_RATE,
        **_NOT_FOUND_SESI,
        **_FORBIDDEN_SESI,
        422: {"model": ErrorResponse, "description": "Sesi bukan TAHAP2 / kode task tidak valid."},
    },
)
def submit_tahap2_keputusan(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    payload: TiTahap2Submit,
    principal: Annotated[Principal, Depends(get_current_principal)],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    seleksi_service: Annotated[TiSeleksiService, Depends(get_ti_seleksi_service)],
    catalog: Annotated[TiCatalogService, Depends(get_ti_catalog_service)],
    tahap2_service: Annotated[TiTahap2Service, Depends(get_ti_tahap2_service)],
    usulan_service: Annotated[TiUsulanService, Depends(get_ti_usulan_service)],
) -> TiTahap2ReviewRead:
    sesi = sesi_service.get(sesi_id)
    if "admin" not in principal.groups:
        par = par_service.get_by_subject(principal.subject)
        if par is None or par.id != sesi.koordinator_id:
            raise ForbiddenError(
                "Akses ditolak: hanya admin atau koordinator SME panel"
                " yang dapat submit keputusan Tahap 2."
            )
    if sesi.status != "TAHAP2":
        raise ValidationAppError(
            f"Keputusan koordinator hanya dapat disubmit saat sesi berstatus TAHAP2"
            f" (saat ini: {sesi.status})."
        )
    if not payload.keputusan and not payload.keputusan_usulan:
        raise ValidationAppError(
            "Payload tidak boleh kosong: isi 'keputusan' dan/atau 'keputusan_usulan'."
        )
    n_submitted = rsp_service.count_tahap1_submitted(sesi_id)
    partial = seleksi_service.partial_terpilih(sesi_id, n_submitted)
    partial_set = set(partial)
    submitted_kodes = {k.task_kode for k in payload.keputusan}
    non_partial = submitted_kodes - partial_set
    if non_partial:
        raise ValidationAppError(
            f"Task berikut bukan task partial (sudah dipilih semua atau tidak ada di seleksi): "
            f"{', '.join(sorted(non_partial)[:5])}"
        )
    # Validasi kepemilikan usulan SEBELUM menyimpan apa pun — payload ditolak utuh
    # (bukan sebagian) bila ada usulan_id yang bukan milik sesi ini.
    usulan_ids_payload = {k.usulan_id for k in payload.keputusan_usulan}
    sesi_usulan_ids = {u.id for u in usulan_service.list_by_sesi(sesi_id)}
    unknown_usulan = usulan_ids_payload - sesi_usulan_ids
    if unknown_usulan:
        raise ValidationAppError(
            f"Usulan berikut bukan milik sesi ini: {', '.join(sorted(unknown_usulan)[:5])}"
            + ("..." if len(unknown_usulan) > 5 else ".")
        )
    valid_kodes = catalog.valid_kodes_for_jabatan(sesi.jabatan_id)
    result = tahap2_service.submit_keputusan(sesi_id, payload.keputusan, valid_kodes)

    usulan_reviews = [
        _to_usulan_review(usulan_service.set_keputusan(item.usulan_id, item.disetujui), rsp_service)
        for item in payload.keputusan_usulan
    ]
    return result.model_copy(update={"usulan": usulan_reviews})
