"""Endpoint proses & langkah redesain (sheet ALUR): khusus `tim-kajian`, tanpa DELETE.

Dua router: `router` di-mount ke `/redesain/proses` dan `router_langkah` ke
`/redesain/langkah`. Langkah yang tak berlaku diberi status `Tidak berlaku`, tidak dihapus.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response

from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_kode_orang_pemanggil,
    get_koreksi_service,
    get_proses_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
    require_tim_kajian_atau_pengisi,
)
from ...etag import check_if_match, compute_etag
from ...redesain.schemas.koreksi import KoreksiCreate, KoreksiRead
from ...redesain.schemas.kosakata import GRUP_TIM_KAJIAN
from ...redesain.schemas.proses import (
    LangkahCreate,
    LangkahRead,
    LangkahUpdate,
    ProsesCreate,
    ProsesRead,
    ProsesUpdate,
)
from ...redesain.services.koreksi import KoreksiService
from ...redesain.services.proses import ProsesService
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ...security import Principal
from ..concurrency import (
    IDEMPOTENCY_RESPONSES,
    PRECONDITION_RESPONSES,
    IfMatchHeader,
    run_idempotent,
)

router = APIRouter()
router_langkah = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Proses tidak ditemukan."}}
_INVALID = {
    422: {
        "model": ErrorResponse,
        "description": (
            "Payload tidak valid / masalah atau sekolah tak dikenal / sekolah proses "
            "berbeda dari sekolah masalah."
        ),
    }
}
_CONFLICT = {409: {"model": ErrorResponse, "description": "Kode hasil bangkitan bentrok."}}


@router.get(
    "",
    response_model=Page[ProsesRead],
    summary="Daftar proses redesain (tim-kajian)",
    operation_id="redesain_proses_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_proses(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[ProsesService, Depends(get_proses_service)],
) -> Page[ProsesRead]:
    """Daftar proses berurutan menurut kode, masing-masing beserta langkahnya."""
    items, total = service.list(limit=page.limit, offset=page.offset)
    return Page[ProsesRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=ProsesRead,
    status_code=201,
    summary="Tambah proses redesain (tim-kajian)",
    operation_id="redesain_proses_create",
    dependencies=_WRITE,
    responses={**IDEMPOTENCY_RESPONSES, **_AUTH, **_RATE, **_FORBIDDEN, **_INVALID, **_CONFLICT},
)
def create_proses(
    data: ProsesCreate,
    service: Annotated[ProsesService, Depends(get_proses_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> ProsesRead:
    """Buat proses baru untuk satu masalah × sekolah; `kode` dibangkitkan global (`P-001`).

    `sekolah_id` wajib sama dengan `masalah.sekolah_id` bila masalah sudah bersekolah;
    masalah tanpa sekolah menerima sekolah mana pun. Selisih → 422. Riwayat
    `entitas="proses"` dicatat.
    """

    def _aksi() -> ProsesRead:
        return service.create(data, pelaku_kode_orang=pelaku)

    return run_idempotent(idem, response, ProsesRead, _aksi)


@router.post(
    "/search",
    response_model=Page[ProsesRead],
    summary="Cari proses (domain ala Odoo) (tim-kajian)",
    operation_id="redesain_proses_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_proses(
    req: SearchRequest,
    service: Annotated[ProsesService, Depends(get_proses_service)],
) -> Page[ProsesRead]:
    """Cari dengan domain ala Odoo; field: masalah_id, sekolah_id, kode."""
    items, total = service.search(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[ProsesRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{proses_id}",
    response_model=ProsesRead,
    summary="Detail proses redesain beserta langkah (tim-kajian)",
    operation_id="redesain_proses_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_proses(
    proses_id: str,
    service: Annotated[ProsesService, Depends(get_proses_service)],
    response: Response,
) -> ProsesRead:
    """Ambil satu proses beserta `langkah` terurut `urutan`."""
    item = service.get(proses_id)
    response.headers["ETag"] = compute_etag(item)
    return item


@router.patch(
    "/{proses_id}",
    response_model=ProsesRead,
    summary="Ubah proses redesain (tim-kajian)",
    operation_id="redesain_proses_update",
    dependencies=_WRITE,
    responses={**PRECONDITION_RESPONSES, **_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND, **_INVALID},
)
def update_proses(
    proses_id: str,
    data: ProsesUpdate,
    service: Annotated[ProsesService, Depends(get_proses_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: IfMatchHeader = None,
) -> ProsesRead:
    """Ubah parsial proses; `kode` read-only, aturan sekolah↔masalah divalidasi ulang."""
    check_if_match(service.get(proses_id), if_match, settings.require_if_match)
    item = service.update(proses_id, data, pelaku_kode_orang=pelaku)
    response.headers["ETag"] = compute_etag(item)
    return item


@router.post(
    "/{proses_id}/langkah",
    response_model=LangkahRead,
    status_code=201,
    summary="Tambah langkah pada proses redesain (tim-kajian)",
    operation_id="redesain_langkah_create",
    dependencies=_WRITE,
    responses={**IDEMPOTENCY_RESPONSES, **_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND, **_CONFLICT},
)
def create_langkah(
    proses_id: str,
    data: LangkahCreate,
    service: Annotated[ProsesService, Depends(get_proses_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> LangkahRead:
    """Tambah langkah; `kode` dibangkitkan per proses (`P-001-S01`, `-S02`, ...).

    `status_langkah` wajib dari kosakata `StatusLangkah` (nilai lain → 422). Riwayat
    `entitas="langkah"` dicatat.
    """

    def _aksi() -> LangkahRead:
        return service.tambah_langkah(proses_id, data, pelaku_kode_orang=pelaku)

    return run_idempotent(idem, response, LangkahRead, _aksi)


@router_langkah.get(
    "/{langkah_id}",
    response_model=LangkahRead,
    summary="Detail langkah proses redesain (tim-kajian); sumber ETag untuk PATCH",
    operation_id="redesain_langkah_get",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Langkah tidak ditemukan."},
    },
)
def get_langkah(
    langkah_id: str,
    service: Annotated[ProsesService, Depends(get_proses_service)],
    response: Response,
) -> LangkahRead:
    """Ambil satu langkah beserta header `ETag`-nya (dipakai `If-Match` pada PATCH)."""
    item = service.get_langkah(langkah_id)
    response.headers["ETag"] = compute_etag(item)
    return item


@router_langkah.patch(
    "/{langkah_id}",
    response_model=LangkahRead,
    summary="Ubah langkah proses redesain (tim-kajian)",
    operation_id="redesain_langkah_update",
    dependencies=_WRITE,
    responses={
        **PRECONDITION_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Langkah tidak ditemukan."},
        422: {"model": ErrorResponse, "description": "Payload tidak valid."},
    },
)
def update_langkah(
    langkah_id: str,
    data: LangkahUpdate,
    service: Annotated[ProsesService, Depends(get_proses_service)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    settings: Annotated[Settings, Depends(get_settings)],
    response: Response,
    if_match: IfMatchHeader = None,
) -> LangkahRead:
    """Ubah parsial langkah; `kode`/`proses_id` read-only. Riwayat dicatat."""
    check_if_match(service.get_langkah(langkah_id), if_match, settings.require_if_match)
    item = service.update_langkah(langkah_id, data, pelaku_kode_orang=pelaku)
    response.headers["ETag"] = compute_etag(item)
    return item


@router_langkah.post(
    "/{langkah_id}/koreksi",
    response_model=KoreksiRead,
    status_code=201,
    summary="Tulis koreksi untuk satu langkah (tim-kajian atau sekolah-pengisi)",
    operation_id="redesain_langkah_koreksi_create",
    dependencies=[Depends(rate_limit)],
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        403: {
            "model": ErrorResponse,
            "description": (
                "Tanpa `konfirmasi_id` (pengisi), konfirmasi bukan milik pemanggil, atau "
                "langkah di luar masalah/sekolah konfirmasi."
            ),
        },
        404: {"model": ErrorResponse, "description": "Langkah/konfirmasi tidak ditemukan."},
        409: {
            "model": ErrorResponse,
            "description": "Dugaan belum ditampilkan (`DUGAAN_BELUM_DITAMPILKAN`).",
        },
        422: {"model": ErrorResponse, "description": "`isi` kosong."},
    },
)
def create_koreksi_langkah(
    langkah_id: str,
    data: KoreksiCreate,
    principal: Annotated[Principal, Depends(require_tim_kajian_atau_pengisi)],
    pelaku: Annotated[str, Depends(get_kode_orang_pemanggil)],
    service: Annotated[KoreksiService, Depends(get_koreksi_service)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> KoreksiRead:
    """Tambah koreksi append-only; isi langkah TIDAK berubah.

    `tim-kajian` boleh tanpa `konfirmasi_id` (tersimpan NULL). `sekolah-pengisi` wajib
    menyertakan `konfirmasi_id` miliknya yang dugaannya sudah tampil, untuk masalah dan
    sekolah yang sama dengan proses langkah itu. Riwayat `entitas="koreksi_langkah"`.
    """

    def _aksi() -> KoreksiRead:
        if GRUP_TIM_KAJIAN in principal.groups:
            return service.tambah_oleh_tim(langkah_id, data.isi, kode_orang=pelaku)
        return service.tambah_oleh_pengisi(
            langkah_id, data.isi, data.konfirmasi_id, kode_orang=pelaku
        )

    return run_idempotent(idem, response, KoreksiRead, _aksi)


@router_langkah.get(
    "/{langkah_id}/koreksi",
    response_model=Page[KoreksiRead],
    summary="Daftar koreksi sebuah langkah (tim-kajian)",
    operation_id="redesain_langkah_koreksi_list",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Langkah tidak ditemukan."},
    },
)
def list_koreksi_langkah(
    langkah_id: str,
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[KoreksiService, Depends(get_koreksi_service)],
) -> Page[KoreksiRead]:
    """Seluruh koreksi langkah (Tim maupun sekolah) terurut `waktu`."""
    items, total = service.list_by_langkah(langkah_id, limit=page.limit, offset=page.offset)
    return Page[KoreksiRead](items=items, total=total, limit=page.limit, offset=page.offset)
