"""Endpoint register klarifikasi narasi: khusus `tim-kajian`, tanpa PATCH/DELETE.

Pertanyaan disusun di aplikasi, disetujui reviewer yang bukan pembuatnya, dikirim fasilitator
DI LUAR aplikasi, lalu jawaban mentah dicatat dengan `response_ref`. Koreksi = batalkan lalu
buat baru. Pengiriman lewat aplikasi di luar lingkup (menunggu OD-12).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_current_principal,
    get_klarifikasi_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...narasi.schemas.klarifikasi import (
    BatalkanKlarifikasi,
    Disposition,
    JawabanKlarifikasi,
    KlarifikasiCreate,
    KlarifikasiDariUsulan,
    KlarifikasiDetail,
    KlarifikasiRead,
    PersetujuanKlarifikasi,
)
from ...narasi.services.klarifikasi import KlarifikasiService
from ...schemas.common import ErrorResponse, Page
from ...security import Principal
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_404 = {404: {"model": ErrorResponse, "description": "Klarifikasi tidak ditemukan."}}
_422 = {422: {"model": ErrorResponse, "description": "Payload tidak valid."}}


@router.post(
    "",
    response_model=KlarifikasiDetail,
    status_code=201,
    summary="Susun pertanyaan klarifikasi (tim-kajian)",
    operation_id="narasi_klarifikasi_create",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_422,
        404: {"model": ErrorResponse, "description": "Kasus narasi tidak ditemukan."},
        409: {
            "model": ErrorResponse,
            "description": "Sudah ada klarifikasi terbuka untuk klaim itu (`KLARIFIKASI_GANDA`) "
            "atau Idempotency-Key sedang diproses.",
        },
    },
)
def create_klarifikasi(
    data: KlarifikasiCreate,
    service: Annotated[KlarifikasiService, Depends(get_klarifikasi_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> KlarifikasiDetail:
    """Simpan pertanyaan `MENUNGGU`/`TERBUKA`; pembuat selalu subjek token."""

    def _aksi() -> KlarifikasiDetail:
        return service.create(data, dibuat_oleh=principal.subject)

    return run_idempotent(idem, response, KlarifikasiDetail, _aksi)


@router.post(
    "/dari-usulan/{ai_usulan_id}",
    response_model=KlarifikasiDetail,
    status_code=201,
    summary="Terapkan usulan P04 yang diterima menjadi klarifikasi (tim-kajian)",
    operation_id="narasi_klarifikasi_dari_usulan",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Usulan atau kasus sasarannya tak ada."},
        409: {
            "model": ErrorResponse,
            "description": "`USULAN_BELUM_DITERIMA`, `USULAN_SUDAH_DITERAPKAN` "
            "(`details[0].msg` = id klarifikasi), `KLARIFIKASI_GANDA`, "
            "atau Idempotency-Key sedang diproses.",
        },
        422: {
            "model": ErrorResponse,
            "description": "Badan tidak sah; `USULAN_BUKAN_P04`; `USULAN_TIDAK_MATERIAL`; "
            "`PERIODE_TAK_ADA`; `ISIAN_USULAN_KURANG`.",
        },
    },
)
def terapkan_usulan_p04(
    ai_usulan_id: str,
    data: KlarifikasiDariUsulan,
    service: Annotated[KlarifikasiService, Depends(get_klarifikasi_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> KlarifikasiDetail:
    """Buat SATU baris register dari usulan P04 yang sudah diterima reviewer.

    Pemetaan field tetap; pembuat adalah subjek token. Urutan cek: usulan 404, bukan P04 422,
    belum diterima 409, tidak material 422, sudah diterapkan 409, periode/isian kurang 422,
    klaim sudah punya klarifikasi terbuka 409. Pemeriksaan berada di dalam aksi idempoten.
    """

    def _aksi() -> KlarifikasiDetail:
        return service.dari_usulan(ai_usulan_id, data, dibuat_oleh=principal.subject)

    return run_idempotent(idem, response, KlarifikasiDetail, _aksi)


@router.get(
    "",
    response_model=Page[KlarifikasiRead],
    summary="Daftar klarifikasi (tim-kajian)",
    operation_id="narasi_klarifikasi_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_klarifikasi(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[KlarifikasiService, Depends(get_klarifikasi_service)],
    narasi_id: Annotated[str | None, Query(description="Saring per kasus narasi.")] = None,
    disposition: Annotated[Disposition | None, Query(description="Saring per disposisi.")] = None,
) -> Page[KlarifikasiRead]:
    """Daftar klarifikasi terbaru dulu; filter opsional `narasi_id` dan `disposition`."""
    items, total = service.daftar(
        narasi_id=narasi_id, disposition=disposition, limit=page.limit, offset=page.offset
    )
    return Page[KlarifikasiRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.get(
    "/{klarifikasi_id}",
    response_model=KlarifikasiDetail,
    summary="Detail klarifikasi beserta riwayat (tim-kajian)",
    operation_id="narasi_klarifikasi_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_404},
)
def get_klarifikasi(
    klarifikasi_id: str,
    service: Annotated[KlarifikasiService, Depends(get_klarifikasi_service)],
) -> KlarifikasiDetail:
    """Satu klarifikasi: 13 metadata, `question_text`, status, dan `riwayat[]` terlama dulu."""
    return service.get(klarifikasi_id)


@router.post(
    "/{klarifikasi_id}/persetujuan",
    response_model=KlarifikasiDetail,
    summary="Setujui atau tolak pertanyaan klarifikasi (reviewer lain)",
    operation_id="narasi_klarifikasi_persetujuan",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_404,
        **_422,
        409: {
            "model": ErrorResponse,
            "description": "`REVIEWER_TIDAK_INDEPENDEN`, `PERSETUJUAN_SUDAH_ADA`, "
            "atau `KLARIFIKASI_TIDAK_TERBUKA`.",
        },
    },
)
def putuskan_klarifikasi(
    klarifikasi_id: str,
    data: PersetujuanKlarifikasi,
    service: Annotated[KlarifikasiService, Depends(get_klarifikasi_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> KlarifikasiDetail:
    """Putuskan persetujuan; subjek token tidak boleh sama dengan pembuat pertanyaan.

    `TOLAK` menutup baris (`disposition=DITOLAK`) sehingga klaim yang sama bebas diberi
    klarifikasi baru; baris `DITOLAK` tak dapat disetujui, dijawab, atau dibatalkan lagi.
    """

    def _aksi() -> KlarifikasiDetail:
        return service.putuskan(klarifikasi_id, data, reviewer=principal.subject)

    return run_idempotent(idem, response, KlarifikasiDetail, _aksi)


@router.post(
    "/{klarifikasi_id}/jawaban",
    response_model=KlarifikasiDetail,
    summary="Catat jawaban mentah klarifikasi (tim-kajian)",
    operation_id="narasi_klarifikasi_jawaban",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_404,
        **_422,
        409: {
            "model": ErrorResponse,
            "description": "`KLARIFIKASI_BELUM_DISETUJUI` atau `KLARIFIKASI_TIDAK_TERBUKA`.",
        },
    },
)
def catat_jawaban(
    klarifikasi_id: str,
    data: JawabanKlarifikasi,
    service: Annotated[KlarifikasiService, Depends(get_klarifikasi_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> KlarifikasiDetail:
    """Catat `response_ref` dan `jawaban_mentah`; disposisi menjadi `TERJAWAB`."""

    def _aksi() -> KlarifikasiDetail:
        return service.catat_jawaban(klarifikasi_id, data, pencatat=principal.subject)

    return run_idempotent(idem, response, KlarifikasiDetail, _aksi)


@router.post(
    "/{klarifikasi_id}/batalkan",
    response_model=KlarifikasiDetail,
    summary="Batalkan pertanyaan klarifikasi terbuka (tim-kajian)",
    operation_id="narasi_klarifikasi_batalkan",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_404,
        **_422,
        409: {"model": ErrorResponse, "description": "`KLARIFIKASI_TIDAK_TERBUKA`."},
    },
)
def batalkan_klarifikasi(
    klarifikasi_id: str,
    data: BatalkanKlarifikasi,
    service: Annotated[KlarifikasiService, Depends(get_klarifikasi_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> KlarifikasiDetail:
    """Batalkan pertanyaan yang masih `TERBUKA`; boleh dibuat ulang untuk klaim yang sama."""

    def _aksi() -> KlarifikasiDetail:
        return service.batalkan(klarifikasi_id, data, pembatal=principal.subject)

    return run_idempotent(idem, response, KlarifikasiDetail, _aksi)
