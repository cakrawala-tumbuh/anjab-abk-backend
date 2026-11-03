"""Endpoint resource `TiResponden`."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status

from ...anjab.services.sme_panel import SMEPanelService
from ...config import Settings, get_settings
from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    authorize_responden_access,
    authorize_sesi_access,
    get_current_principal,
    get_kode_orang_service,
    get_partisipan_service,
    get_sme_panel_service,
    get_ti_responden_service,
    get_ti_sesi_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_admin,
)
from ...errors import ValidationAppError
from ...etag import check_if_match, compute_etag
from ...redesain.services.kode_orang import KodeOrangService
from ...schemas.common import BulkAssignResult, BulkSkipped, ErrorResponse, Page
from ...security import Principal
from ...taskinv.schemas.responden import (
    TiRespondenAlihkan,
    TiRespondenBulkCreate,
    TiRespondenCreate,
    TiRespondenRead,
)
from ...taskinv.services.responden import TiRespondenService
from ...taskinv.services.sesi import TiSesiService
from ..concurrency import (
    IDEMPOTENCY_RESPONSES,
    PRECONDITION_RESPONSES,
    IfMatchHeader,
    run_idempotent,
)
from ..kode_orang_isi import isi_kode_orang
from ..pagination import set_pagination_links

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_ADMIN_GUARDS = [Depends(require_admin), Depends(rate_limit)]
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi tidak ditemukan."}}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik responden."}
}
_FORBIDDEN_PESERTA = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau peserta sesi."}
}


@router.get(
    "/{sesi_id}/responden",
    response_model=Page[TiRespondenRead],
    summary="Daftar responden dalam sesi (admin atau peserta sesi)",
    operation_id="taskinv_responden_list",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_FORBIDDEN_PESERTA, **_NOT_FOUND_SESI},
)
def list_responden(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    request: Request,
    response: Response,
    page: Annotated[Pagination, Depends(pagination_params)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
) -> Page[TiRespondenRead]:
    sesi = sesi_service.get(sesi_id)
    authorize_sesi_access(principal, sesi, par_service, rsp_service)
    items, total = rsp_service.list_by_sesi(sesi_id, limit=page.limit, offset=page.offset)
    isi_kode_orang(items, ko_service)
    set_pagination_links(response, request, total, page.limit, page.offset)
    return Page[TiRespondenRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "/{sesi_id}/responden",
    response_model=TiRespondenRead,
    status_code=status.HTTP_201_CREATED,
    summary="Daftarkan responden ke sesi (admin; saat DRAFT/TAHAP1)",
    operation_id="taskinv_responden_create",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_SESI,
        409: {
            "model": ErrorResponse,
            "description": (
                "Partisipan ini sudah terdaftar sebagai responden pada sesi ini,"
                " atau Idempotency-Key sedang diproses."
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": (
                "Partisipan bukan anggota SME panel jabatan sesi ini, atau cabang"
                " sekolah partisipan berbeda dari cabang sesi."
            ),
        },
    },
)
def create_responden(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    payload: TiRespondenCreate,
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    sme_panel_service: Annotated[SMEPanelService, Depends(get_sme_panel_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> TiRespondenRead:
    """Daftarkan satu responden ke sesi Task Inventory `sesi_id` (admin).

    Menolak `422` bila sesi bukan `DRAFT`/`TAHAP1`, bila `payload.partisipan_id`
    diisi tapi bukan anggota SME panel jabatan sesi ini, atau bila cabang sekolah
    partisipan diketahui dan berbeda dari cabang sesi
    (`SqlTiRespondenService.create()`, backlog `anjab-abk-backend#41` — "tidak
    tahu ≠ salah": cabang sesi/partisipan yang tidak diketahui diloloskan).
    Menolak `409` bila `payload.partisipan_id` non-null sudah terdaftar sebagai
    responden di sesi ini (`SqlTiRespondenService.create()`, backlog
    `anjab-abk-backend#29`) — `partisipan_id` kosong (responden manual tanpa
    partisipan) boleh berulang. `Idempotency-Key` opsional: pengulangan dengan key sama
    mengembalikan hasil pertama (200) tanpa mendaftarkan lagi.
    """
    sesi = sesi_service.get(sesi_id)
    if sesi.status not in ("DRAFT", "TAHAP1"):
        raise ValidationAppError(
            "Responden hanya dapat ditambahkan saat sesi berstatus DRAFT atau TAHAP1"
            f" (saat ini: {sesi.status})."
        )
    if sesi.jabatan_id and payload.partisipan_id:
        panels, _ = sme_panel_service.search(
            domain=[["jabatan_id", "=", sesi.jabatan_id]],
            order=[],
            limit=1,
            offset=0,
        )
        if not panels:
            raise ValidationAppError("SME panel untuk jabatan sesi ini belum dibuat.")
        if payload.partisipan_id not in panels[0].partisipan_ids:
            raise ValidationAppError(
                "Partisipan tidak dapat ditambahkan: belum tergabung dalam SME panel jabatan ini."
            )

    def _create() -> TiRespondenRead:
        hasil = rsp_service.create(sesi_id, payload)
        isi_kode_orang([hasil], ko_service, jamin=True)
        return hasil

    return run_idempotent(idem, response, TiRespondenRead, _create)


@router.post(
    "/{sesi_id}/responden/bulk",
    response_model=BulkAssignResult[TiRespondenRead],
    status_code=status.HTTP_201_CREATED,
    summary="Tugaskan banyak partisipan sekaligus sebagai responden (admin; saat DRAFT/TAHAP1)",
    operation_id="taskinv_responden_create_banyak",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_SESI,
        **IDEMPOTENCY_RESPONSES,
        422: {
            "model": ErrorResponse,
            "description": "Sesi bukan DRAFT/TAHAP1.",
        },
    },
)
def create_responden_banyak(
    sesi_id: Annotated[str, Path(description="ID sesi.")],
    payload: TiRespondenBulkCreate,
    sesi_service: Annotated[TiSesiService, Depends(get_ti_sesi_service)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    sme_panel_service: Annotated[SMEPanelService, Depends(get_sme_panel_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> BulkAssignResult[TiRespondenRead]:
    sesi = sesi_service.get(sesi_id)
    if sesi.status not in ("DRAFT", "TAHAP1"):
        raise ValidationAppError(
            "Responden hanya dapat ditambahkan saat sesi berstatus DRAFT atau TAHAP1"
            f" (saat ini: {sesi.status})."
        )

    def _assign() -> BulkAssignResult[TiRespondenRead]:
        anggota_ids: set[str] = set()
        if sesi.jabatan_id:
            panels, _ = sme_panel_service.search(
                domain=[["jabatan_id", "=", sesi.jabatan_id]],
                order=[],
                limit=1,
                offset=0,
            )
            if panels:
                anggota_ids = set(panels[0].partisipan_ids)

        skipped: list[BulkSkipped] = []
        seen: set[str] = set()
        anggota_valid: list[str] = []
        for partisipan_id in payload.partisipan_ids:
            if partisipan_id in seen:
                skipped.append(BulkSkipped(partisipan_id=partisipan_id, alasan="duplikat_input"))
                continue
            seen.add(partisipan_id)
            if partisipan_id not in anggota_ids:
                skipped.append(
                    BulkSkipped(partisipan_id=partisipan_id, alasan="bukan_anggota_sme_panel")
                )
                continue
            anggota_valid.append(partisipan_id)

        result = rsp_service.assign_banyak(sesi_id, anggota_valid)
        result.skipped = skipped + result.skipped
        isi_kode_orang(result.created, ko_service, jamin=True)
        return result

    return run_idempotent(idem, response, BulkAssignResult[TiRespondenRead], _assign)


@router.get(
    "/responden/{responden_id}",
    response_model=TiRespondenRead,
    summary="Ambil detail responden (admin atau pemilik)",
    operation_id="taskinv_responden_get",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def get_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    response: Response,
) -> TiRespondenRead:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    isi_kode_orang([responden], ko_service)
    response.headers["ETag"] = compute_etag(responden)
    return responden


@router.delete(
    "/responden/{responden_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus responden (admin; hanya jika belum submit)",
    operation_id="taskinv_responden_delete",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND_RSP, **PRECONDITION_RESPONSES},
)
def delete_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    if_match: IfMatchHeader = None,
) -> Response:
    responden = rsp_service.get(responden_id)
    isi_kode_orang([responden], ko_service)
    check_if_match(responden, if_match, settings.require_if_match)
    rsp_service.delete(responden_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/responden/{responden_id}/alihkan",
    response_model=TiRespondenRead,
    summary="Alihkan responden ke partisipan lain (admin; jawaban & status kirim tetap utuh)",
    operation_id="taskinv_responden_alihkan",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        404: {
            "model": ErrorResponse,
            "description": "Responden atau partisipan tujuan tidak ditemukan.",
        },
        409: {
            "model": ErrorResponse,
            "description": (
                "Partisipan tujuan sudah terdaftar sebagai responden pada sesi ini,"
                " atau Idempotency-Key sedang diproses."
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": (
                "`dari_partisipan_id` sama dengan `ke_partisipan_id`, responden bukan"
                " milik `dari_partisipan_id` saat ini, atau partisipan tujuan tidak aktif."
            ),
        },
    },
)
def alihkan_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    payload: TiRespondenAlihkan,
    rsp_service: Annotated[TiRespondenService, Depends(get_ti_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> TiRespondenRead:
    """Alihkan kepemilikan responden `responden_id` dari `dari_partisipan_id` ke
    `ke_partisipan_id` (admin).

    Seluruh jawaban (`ti_detail`/`ti_seleksi`/`ti_usulan_task`, yang merujuk
    `responden_id`, bukan `partisipan_id`) dan status/timestamp kirim
    (`tahap1_submit`/`tahap3_submit` beserta timestamp-nya) tetap utuh — hanya
    `partisipan_id`/`nama` pada baris responden yang berubah (backlog `#47`,
    asal `ypii-support#73`). Sah dipanggil di sesi status apa pun; keanggotaan
    SME panel partisipan tujuan TIDAK diperiksa (ini koreksi kepemilikan oleh
    admin, bukan pendaftaran baru).

    Urutan validasi (`## Keputusan Desain` `anjab-abk-backend#47`): responden
    tidak ada → 404; `dari_partisipan_id == ke_partisipan_id` → 422; responden
    bukan milik `dari_partisipan_id` saat ini → 422 (pesan menyebut pemilik
    aktual); partisipan tujuan tidak ada → 404; partisipan tujuan nonaktif →
    422; partisipan tujuan sudah jadi responden di sesi yang sama → 409
    (`TiRespondenService.alihkan()`). `Idempotency-Key` opsional: pengulangan dengan key
    sama mengembalikan hasil pertama (200) tanpa mengalihkan lagi.
    """
    responden = rsp_service.get(responden_id)
    if payload.dari_partisipan_id == payload.ke_partisipan_id:
        raise ValidationAppError("Partisipan asal dan tujuan tidak boleh sama.")
    if responden.partisipan_id != payload.dari_partisipan_id:
        raise ValidationAppError(
            "Responden ini bukan milik partisipan"
            f" '{payload.dari_partisipan_id}' (pemilik saat ini:"
            f" {responden.partisipan_id!r})."
        )
    partisipan_b = par_service.get(payload.ke_partisipan_id)
    if not partisipan_b.aktif:
        raise ValidationAppError(f"Partisipan '{payload.ke_partisipan_id}' tidak aktif.")

    def _alihkan() -> TiRespondenRead:
        hasil = rsp_service.alihkan(responden_id, payload.ke_partisipan_id, partisipan_b.nama)
        isi_kode_orang([hasil], ko_service, jamin=True)
        return hasil

    return run_idempotent(idem, response, TiRespondenRead, _alihkan)
