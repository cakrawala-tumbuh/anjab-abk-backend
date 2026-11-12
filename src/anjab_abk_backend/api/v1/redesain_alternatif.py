"""Endpoint alternatif redesain: khusus `tim-kajian`, tanpa DELETE."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_alternatif_service,
    get_kode_orang_pemanggil,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...etag import check_if_match, compute_etag
from ...fitur import FiturKode, require_fitur
from ...redesain.schemas.alternatif import (
    POLA_PERIODE,
    AlternatifCreate,
    AlternatifRead,
    AlternatifUpdate,
    KeputusanPerubahanCreate,
    KeputusanPerubahanRead,
    KesiapanCreate,
    KesiapanMatriksRead,
    KesiapanRead,
    PenerimaCreate,
    PenerimaRead,
)
from ...redesain.services.alternatif import AlternatifService
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ..concurrency import (
    IDEMPOTENCY_RESPONSES,
    PRECONDITION_RESPONSES,
    IfMatchHeader,
    run_idempotent,
)

router = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Alternatif tidak ditemukan."}}


@router.get(
    "",
    response_model=Page[AlternatifRead],
    summary="Daftar alternatif redesain (tim-kajian)",
    operation_id="redesain_alternatif_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_alternatif(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
) -> Page[AlternatifRead]:
    """Daftar alternatif berurutan menurut kode."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[AlternatifRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=AlternatifRead,
    status_code=201,
    summary="Tambah alternatif redesain (tim-kajian)",
    operation_id="redesain_alternatif_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {"model": ErrorResponse, "description": "Kode alternatif bentrok."},
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def create_alternatif(
    data: AlternatifCreate,
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> AlternatifRead:
    """Buat alternatif baru (kode `U-NNN`); 422 bila rujukan atau aturan opsi/status tak valid."""

    def _aksi() -> AlternatifRead:
        return service.create(data, pelaku_kode_orang=pelaku)

    return run_idempotent(idem, response, AlternatifRead, _aksi)


@router.post(
    "/search",
    response_model=Page[AlternatifRead],
    summary="Cari alternatif (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_alternatif_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_alternatif(
    req: SearchRequest,
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
) -> Page[AlternatifRead]:
    """Cari dengan domain ala Odoo; field di-whitelist, nilai bound parameter."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[AlternatifRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{alternatif_id}",
    response_model=AlternatifRead,
    summary="Detail alternatif redesain (tim-kajian)",
    operation_id="redesain_alternatif_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_alternatif(
    alternatif_id: str,
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
    response: Response,
) -> AlternatifRead:
    """Ambil satu alternatif."""
    item = service.get(alternatif_id)
    response.headers["ETag"] = compute_etag(item)
    return item


@router.patch(
    "/{alternatif_id}",
    response_model=AlternatifRead,
    summary="Ubah alternatif redesain (tim-kajian)",
    operation_id="redesain_alternatif_update",
    dependencies=_WRITE,
    responses={**PRECONDITION_RESPONSES, **_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def update_alternatif(
    alternatif_id: str,
    data: AlternatifUpdate,
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: IfMatchHeader = None,
) -> AlternatifRead:
    """Ubah parsial alternatif (mis. status telaah); `kode` dan `masalah_id` tetap."""
    check_if_match(service.get(alternatif_id), if_match, settings.require_if_match)
    item = service.update(alternatif_id, data, pelaku_kode_orang=pelaku)
    response.headers["ETag"] = compute_etag(item)
    return item


@router.get(
    "/{alternatif_id}/penerima",
    response_model=list[PenerimaRead],
    summary="Daftar penerima alternatif redesain (tim-kajian)",
    operation_id="redesain_alternatif_penerima_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def list_penerima(
    alternatif_id: str,
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
) -> list[PenerimaRead]:
    """Daftar penerima (jabatan) alternatif, urut waktu penambahan."""
    return service.daftar_penerima(alternatif_id)


@router.post(
    "/{alternatif_id}/penerima",
    response_model=PenerimaRead,
    status_code=201,
    summary="Tambah penerima alternatif redesain (tim-kajian)",
    operation_id="redesain_alternatif_penerima_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        409: {
            "model": ErrorResponse,
            "description": "Jabatan sudah menjadi penerima (`PENERIMA_GANDA`).",
        },
        422: {"model": ErrorResponse, "description": "Payload/jabatan tidak valid."},
    },
)
def create_penerima(
    alternatif_id: str,
    data: PenerimaCreate,
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> PenerimaRead:
    """Tambah satu jabatan penerima; kolom lama `pihak_penerima_jabatan_id` tidak disentuh."""

    def _aksi() -> PenerimaRead:
        return service.tambah_penerima(alternatif_id, data)

    return run_idempotent(idem, response, PenerimaRead, _aksi)


@router.post(
    "/{alternatif_id}/kesiapan",
    response_model=KesiapanRead,
    status_code=201,
    summary="Catat penilaian kesiapan penerima per periode (tim-kajian)",
    operation_id="redesain_alternatif_kesiapan_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        422: {
            "model": ErrorResponse,
            "description": "Aturan wajib-isi dilanggar atau `PENERIMA_BUKAN_MILIK_ALTERNATIF`.",
        },
    },
)
def create_kesiapan(
    alternatif_id: str,
    data: KesiapanCreate,
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> KesiapanRead:
    """Catat penilaian kesiapan (append-only); koreksi = penilaian baru, matriks memakai terakhir.

    `NOT_ESTIMABLE` menyimpan nilai null (bukan 0).
    """

    def _aksi() -> KesiapanRead:
        return service.nilai_kesiapan(alternatif_id, data, dinilai_oleh=pelaku)

    return run_idempotent(idem, response, KesiapanRead, _aksi)


@router.get(
    "/{alternatif_id}/kesiapan",
    response_model=KesiapanMatriksRead,
    summary="Matriks kesiapan alternatif per periode beserta status opsi (tim-kajian)",
    operation_id="redesain_alternatif_kesiapan_matriks",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        422: {"model": ErrorResponse, "description": "`periode` hilang atau salah pola."},
    },
)
def get_matriks_kesiapan(
    alternatif_id: str,
    periode: Annotated[str, Query(pattern=POLA_PERIODE, description="Periode, mis. 2026/27.")],
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
) -> KesiapanMatriksRead:
    """Matriks kesiapan pada periode: penilaian terakhir per penerima dan `status_opsi`."""
    return service.matriks_kesiapan(alternatif_id, periode)


@router.post(
    "/{alternatif_id}/keputusan-perubahan",
    response_model=KeputusanPerubahanRead,
    status_code=201,
    summary="Catat keputusan perubahan alternatif per periode (tim-kajian)",
    operation_id="redesain_alternatif_keputusan_perubahan_create",
    dependencies=[*_WRITE, Depends(require_fitur(FiturKode.CHANGE_AUTHORIZATION))],
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        409: {
            "model": ErrorResponse,
            "description": (
                "Saklar `CHANGE_AUTHORIZATION` mati (`feature_disabled`), APPROVE saat opsi "
                "belum READY (`KESIAPAN_BELUM_READY`), atau CONDITIONAL saat opsi HOLD "
                "(`KESIAPAN_HOLD`)."
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": "Payload tidak valid (mis. `stop_rule` kosong pada CONDITIONAL).",
        },
    },
)
def create_keputusan_perubahan(
    alternatif_id: str,
    data: KeputusanPerubahanCreate,
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> KeputusanPerubahanRead:
    """Catat keputusan perubahan (append-only), ditegakkan terhadap status opsi periode itu.

    Tidak pernah tercipta dari keputusan prioritas (`POST /redesain/penilaian/{id}/putuskan`).
    """

    def _aksi() -> KeputusanPerubahanRead:
        return service.putuskan_perubahan(alternatif_id, data, pemutus=pelaku)

    return run_idempotent(idem, response, KeputusanPerubahanRead, _aksi)


@router.get(
    "/{alternatif_id}/keputusan-perubahan",
    response_model=list[KeputusanPerubahanRead],
    summary="Riwayat keputusan perubahan alternatif (tim-kajian)",
    operation_id="redesain_alternatif_keputusan_perubahan_list",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        422: {"model": ErrorResponse, "description": "`periode` salah pola."},
    },
)
def list_keputusan_perubahan(
    alternatif_id: str,
    service: Annotated[AlternatifService, Depends(get_alternatif_service)],
    periode: Annotated[
        str | None, Query(pattern=POLA_PERIODE, description="Saring per periode, mis. 2026/27.")
    ] = None,
) -> list[KeputusanPerubahanRead]:
    """Riwayat urut `created_at` naik; keputusan berlaku = baris terakhir per periode.

    Tidak digerbang saklar: riwayat tetap terbaca saat `CHANGE_AUTHORIZATION` mati.
    """
    return service.riwayat_keputusan_perubahan(alternatif_id, periode)
