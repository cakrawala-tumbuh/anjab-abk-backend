"""Endpoint resource `OpmResponden` dan submit jawaban."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request, Response, status

from ...config import Settings, get_settings
from ...core.services.partisipan import PartisipanService
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    authorize_responden_access,
    get_current_principal,
    get_kode_orang_service,
    get_opm_jawaban_service,
    get_opm_responden_service,
    get_opm_sesi_service,
    get_partisipan_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_admin,
)
from ...errors import ValidationAppError
from ...etag import check_if_match, compute_etag
from ...opm.schemas.jawaban import OpmJawabanRead, OpmJawabanUpsert
from ...opm.schemas.responden import (
    OpmRespondenAlihkan,
    OpmRespondenBulkCreate,
    OpmRespondenCreate,
    OpmRespondenRead,
)
from ...opm.services.jawaban import OpmJawabanService
from ...opm.services.responden import OpmRespondenService
from ...opm.services.sesi import OpmSesiService
from ...redesain.services.kode_orang import KodeOrangService
from ...schemas.common import BulkAssignResult, ErrorResponse, Page
from ...security import Principal
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
_NOT_FOUND_SESI = {404: {"model": ErrorResponse, "description": "Sesi OPM tidak ditemukan."}}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik responden."}
}


@router.get(
    "/{sesi_id}/responden",
    response_model=Page[OpmRespondenRead],
    summary="Daftar responden dalam sesi OPM (admin)",
    operation_id="opm_responden_list",
    dependencies=[Depends(require_admin)],
    responses={**_AUTH, **_FORBIDDEN, **_NOT_FOUND_SESI},
)
def list_responden(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    request: Request,
    response: Response,
    page: Annotated[Pagination, Depends(pagination_params)],
    sesi_service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
) -> Page[OpmRespondenRead]:
    sesi_service.get(sesi_id)
    items, total = rsp_service.list_by_sesi(sesi_id, limit=page.limit, offset=page.offset)
    isi_kode_orang(items, ko_service)
    set_pagination_links(response, request, total, page.limit, page.offset)
    return Page[OpmRespondenRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "/{sesi_id}/responden",
    response_model=OpmRespondenRead,
    status_code=status.HTTP_201_CREATED,
    summary="Daftarkan responden manual ke sesi OPM (admin; wajib anggota SME panel jabatan sesi)",
    operation_id="opm_responden_create",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_SESI,
        409: {
            "model": ErrorResponse,
            "description": (
                "Partisipan sudah terdaftar sebagai responden OPM di sesi ini,"
                " atau Idempotency-Key sedang diproses."
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": "Sesi bukan DRAFT/OPEN, atau partisipan bukan anggota SME panel.",
        },
    },
)
def create_responden(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    payload: OpmRespondenCreate,
    sesi_service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> OpmRespondenRead:
    sesi = sesi_service.get(sesi_id)
    if sesi.status not in ("DRAFT", "OPEN"):
        raise ValidationAppError(
            f"Responden hanya dapat ditambahkan saat sesi DRAFT/OPEN (saat ini: {sesi.status})."
        )

    def _create() -> OpmRespondenRead:
        hasil = rsp_service.create(sesi_id, payload, sesi.max_responden, sesi.jabatan_id)
        isi_kode_orang([hasil], ko_service, jamin=True)
        return hasil

    return run_idempotent(idem, response, OpmRespondenRead, _create)


@router.post(
    "/{sesi_id}/responden/bulk",
    response_model=BulkAssignResult[OpmRespondenRead],
    status_code=status.HTTP_201_CREATED,
    summary="Tugaskan banyak partisipan sekaligus sebagai responden OPM (admin, idempoten)",
    operation_id="opm_responden_create_banyak",
    dependencies=_ADMIN_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_SESI,
        **IDEMPOTENCY_RESPONSES,
        422: {
            "model": ErrorResponse,
            "description": "Sesi bukan DRAFT/OPEN.",
        },
    },
)
def create_responden_banyak(
    sesi_id: Annotated[str, Path(description="ID sesi OPM.")],
    payload: OpmRespondenBulkCreate,
    sesi_service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> BulkAssignResult[OpmRespondenRead]:
    sesi = sesi_service.get(sesi_id)
    if sesi.status not in ("DRAFT", "OPEN"):
        raise ValidationAppError(
            f"Responden hanya dapat ditambahkan saat sesi DRAFT/OPEN (saat ini: {sesi.status})."
        )

    def _assign() -> BulkAssignResult[OpmRespondenRead]:
        hasil = rsp_service.assign_banyak(
            sesi_id,
            payload.partisipan_ids,
            max_responden=sesi.max_responden,
            jabatan_id=sesi.jabatan_id,
        )
        isi_kode_orang(hasil.created, ko_service, jamin=True)
        return hasil

    return run_idempotent(idem, response, BulkAssignResult[OpmRespondenRead], _assign)


@router.get(
    "/responden/{responden_id}",
    response_model=OpmRespondenRead,
    summary="Ambil detail responden OPM (admin atau pemilik)",
    operation_id="opm_responden_get",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def get_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    response: Response,
) -> OpmRespondenRead:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    isi_kode_orang([responden], ko_service)
    response.headers["ETag"] = compute_etag(responden)
    return responden


@router.delete(
    "/responden/{responden_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Hapus responden (admin; hanya jika belum submit)",
    operation_id="opm_responden_delete",
    dependencies=_ADMIN_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND_RSP, **PRECONDITION_RESPONSES},
)
def delete_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
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
    response_model=OpmRespondenRead,
    summary="Alihkan responden OPM ke partisipan lain (admin; jawaban & status kirim tetap utuh)",
    operation_id="opm_responden_alihkan",
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
                "Partisipan tujuan sudah terdaftar sebagai responden OPM pada sesi ini,"
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
    payload: OpmRespondenAlihkan,
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    ko_service: Annotated[KodeOrangService, Depends(get_kode_orang_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> OpmRespondenRead:
    """Alihkan kepemilikan responden OPM `responden_id` dari `dari_partisipan_id`
    ke `ke_partisipan_id` (admin).

    Seluruh jawaban `opm_jawaban` (yang merujuk `responden_id`, bukan
    `partisipan_id`) dan status/timestamp kirim (`sudah_submit`/`submitted_at`)
    tetap utuh — hanya `partisipan_id`/`nama` pada baris responden yang berubah
    (backlog `#47`, asal `ypii-support#73`). Sah dipanggil di sesi status apa pun
    dan tanpa memeriksa kuota `max_responden` (mutasi, bukan penambahan — jumlah
    responden sesi tetap sama); keanggotaan SME panel partisipan tujuan TIDAK
    diperiksa (ini koreksi kepemilikan oleh admin, bukan pendaftaran baru).

    Urutan validasi (`## Keputusan Desain` `anjab-abk-backend#47`): responden
    tidak ada → 404; `dari_partisipan_id == ke_partisipan_id` → 422; responden
    bukan milik `dari_partisipan_id` saat ini → 422 (pesan menyebut pemilik
    aktual); partisipan tujuan tidak ada → 404; partisipan tujuan nonaktif →
    422; partisipan tujuan sudah jadi responden OPM di sesi yang sama → 409
    (`OpmRespondenService.alihkan()`). Idempotency-Key opsional: pengulangan dengan key
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

    def _alihkan() -> OpmRespondenRead:
        hasil = rsp_service.alihkan(responden_id, payload.ke_partisipan_id, partisipan_b.nama)
        isi_kode_orang([hasil], ko_service, jamin=True)
        return hasil

    return run_idempotent(idem, response, OpmRespondenRead, _alihkan)


@router.put(
    "/responden/{responden_id}/jawaban",
    response_model=list[OpmJawabanRead],
    summary="Simpan draft rating (Importance/Frequency/Criticality) untuk satu responden",
    operation_id="opm_jawaban_save_draft",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_RSP,
        **PRECONDITION_RESPONSES,
        422: {
            "model": ErrorResponse,
            "description": "Sesi bukan OPEN, responden sudah submit, atau kode task tidak dikenal.",
        },
    },
)
def save_draft_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    payload: OpmJawabanUpsert,
    principal: Annotated[Principal, Depends(get_current_principal)],
    sesi_service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    jwb_service: Annotated[OpmJawabanService, Depends(get_opm_jawaban_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: IfMatchHeader = None,
) -> list[OpmJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    check_if_match(jwb_service.list_by_responden(responden_id), if_match, settings.require_if_match)
    sesi = sesi_service.get(responden.sesi_id)
    if sesi.status != "OPEN":
        raise ValidationAppError(
            f"Jawaban hanya dapat disimpan saat sesi berstatus OPEN (saat ini: {sesi.status})."
        )
    if responden.sudah_submit:
        raise ValidationAppError(
            "Responden ini sudah mengirimkan jawaban; draft tidak bisa diubah."
        )
    valid_task_kodes = sesi_service.get_task_kodes(responden.sesi_id)
    hasil = jwb_service.upsert(responden_id, payload, valid_task_kodes)
    response.headers["ETag"] = compute_etag(jwb_service.list_by_responden(responden_id))
    return hasil


@router.post(
    "/responden/{responden_id}/jawaban/submit",
    response_model=list[OpmJawabanRead],
    status_code=status.HTTP_201_CREATED,
    summary="Finalisasi (submit) rating tersimpan untuk satu responden",
    operation_id="opm_jawaban_submit",
    dependencies=_WRITE_GUARDS,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOT_FOUND_RSP,
        **IDEMPOTENCY_RESPONSES,
        422: {
            "model": ErrorResponse,
            "description": "Sesi bukan OPEN, responden sudah submit, atau set task tidak lengkap.",
        },
    },
)
def submit_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    sesi_service: Annotated[OpmSesiService, Depends(get_opm_sesi_service)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    jwb_service: Annotated[OpmJawabanService, Depends(get_opm_jawaban_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> list[OpmJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)

    def _submit() -> list[OpmJawabanRead]:
        sesi = sesi_service.get(responden.sesi_id)
        if sesi.status != "OPEN":
            raise ValidationAppError(
                f"Jawaban hanya dapat disubmit saat sesi berstatus OPEN (saat ini: {sesi.status})."
            )
        if responden.sudah_submit:
            raise ValidationAppError("Responden ini sudah mengirimkan jawaban.")
        valid_task_kodes = sesi_service.get_task_kodes(responden.sesi_id)
        results = jwb_service.submit(responden_id, valid_task_kodes)
        rsp_service.mark_submitted(responden_id)
        return results

    return run_idempotent(idem, response, list[OpmJawabanRead], _submit)


@router.get(
    "/responden/{responden_id}/jawaban",
    response_model=list[OpmJawabanRead],
    summary="Lihat jawaban responden (admin atau pemilik)",
    operation_id="opm_jawaban_list",
    dependencies=READ_GUARDS,
    responses={**_RATE, **_AUTH, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def list_jawaban(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[OpmRespondenService, Depends(get_opm_responden_service)],
    jwb_service: Annotated[OpmJawabanService, Depends(get_opm_jawaban_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
    response: Response,
) -> list[OpmJawabanRead]:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    jawaban = jwb_service.list_by_responden(responden_id)
    response.headers["ETag"] = compute_etag(jawaban)
    return jawaban
