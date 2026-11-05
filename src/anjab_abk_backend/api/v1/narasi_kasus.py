"""Endpoint kasus narasi (jalur manual F1): khusus `tim-kajian`, tanpa PATCH/DELETE.

Status kasus hanya berpindah lewat `NarasiService`; tidak ada rute yang menetapkannya.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    get_current_principal,
    get_narasi_service,
    get_narasi_sumber_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...errors import NotFoundError, ValidationAppError
from ...narasi.schemas.kasus import NarrativeKind, RevisionOrigin, StatusNarasi
from ...narasi.schemas.mesin import (
    AktorNarasi,
    KutipanSumber,
    NarasiKasusCreate,
    NarasiKasusRead,
    NarasiVersiRead,
)
from ...narasi.schemas.rute import (
    NarasiKasusBuat,
    NarasiKasusDetail,
    NarasiRevisiCreate,
    NarasiRiwayatRead,
    NarasiVersiLengkap,
    SensitivityClass,
)
from ...narasi.services.narasi import (
    JenisBelumDibukaError,
    NarasiService,
    SensitifBelumDibukaError,
)
from ...narasi.services.sumber import NarasiSumberService
from ...schemas.common import ErrorResponse, Page
from ...schemas.search import SearchRequest
from ...security import Principal
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()

ROLE_AKTOR = "REVIEWER"
"""Peran yang dicatat untuk Tim Kajian pada versi/kasus yang ditulis lewat API."""

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Kasus narasi tidak ditemukan."}}


def _aktor(principal: Principal) -> AktorNarasi:
    """Turunkan aktor dari token tervalidasi (bukan dari body)."""
    return AktorNarasi(key=principal.subject, role=ROLE_AKTOR)


def _lengkap(service: NarasiService, versi: NarasiVersiRead) -> NarasiVersiLengkap:
    return NarasiVersiLengkap(**versi.model_dump(), sumber=service.sumber_versi(versi.id))


@router.get(
    "",
    response_model=Page[NarasiKasusRead],
    summary="Daftar kasus narasi (tim-kajian)",
    operation_id="narasi_kasus_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_kasus(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[NarasiService, Depends(get_narasi_service)],
    status: Annotated[StatusNarasi | None, Query(description="Filter status.")] = None,
    instrument_id: Annotated[
        str | None, Query(max_length=50, description="Filter instrumen.")
    ] = None,
    periode: Annotated[str | None, Query(max_length=20, description="Filter periode.")] = None,
) -> Page[NarasiKasusRead]:
    """Daftar kasus terbaru dulu; filter `status`, `instrument_id`, `periode`."""
    items, total = service.list_kasus(
        status=status.value if status else None,
        instrument_id=instrument_id,
        periode=periode,
        limit=page.limit,
        offset=page.offset,
    )
    return Page[NarasiKasusRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.post(
    "",
    response_model=NarasiKasusRead,
    status_code=201,
    summary="Buat kasus narasi F1 nonpribadi (tim-kajian)",
    operation_id="narasi_kasus_create",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        409: {"model": ErrorResponse, "description": "Lingkup ganda (narasi_lingkup_ganda)."},
        422: {
            "model": ErrorResponse,
            "description": (
                "Payload tidak valid; jenis selain F1_FORMAL (narasi_jenis_belum_dibuka) "
                "atau SENSITIF (narasi_sensitif_belum_dibuka)."
            ),
        },
    },
)
def create_kasus(
    data: NarasiKasusBuat,
    service: Annotated[NarasiService, Depends(get_narasi_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> NarasiKasusRead:
    """Buat kasus berstatus `SOURCE_CHECKED`; `dibuat_oleh` diambil dari token.

    Hanya `F1_FORMAL` dan `NONPRIBADI` yang dibuka (K-1); lainnya 422.
    """
    if data.narrative_kind != NarrativeKind.F1_FORMAL:
        raise JenisBelumDibukaError("Hanya narrative_kind F1_FORMAL yang dibuka.")
    if data.sensitivity_class != SensitivityClass.NONPRIBADI:
        raise SensitifBelumDibukaError("Kasus SENSITIF belum dibuka.")
    payload = NarasiKasusCreate(**data.model_dump(mode="json"))

    def _aksi() -> NarasiKasusRead:
        return service.buat_kasus(payload, _aktor(principal))

    return run_idempotent(idem, response, NarasiKasusRead, _aksi)


@router.post(
    "/search",
    response_model=Page[NarasiKasusRead],
    summary="Cari kasus narasi (domain ala Odoo) (tim-kajian)",
    operation_id="narasi_kasus_search",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {"model": ErrorResponse, "description": "Domain/field tidak valid."},
    },
)
def search_kasus(
    req: SearchRequest,
    service: Annotated[NarasiService, Depends(get_narasi_service)],
) -> Page[NarasiKasusRead]:
    """Cari dengan domain ala Odoo; field di-whitelist."""
    items, total = service.search_kasus(
        domain=req.domain, order=req.order, limit=req.limit, offset=req.offset
    )
    return Page[NarasiKasusRead](items=items, total=total, limit=req.limit, offset=req.offset)


@router.get(
    "/{narasi_id}",
    response_model=NarasiKasusDetail,
    summary="Detail kasus narasi dengan versi terbaru dan sumbernya (tim-kajian)",
    operation_id="narasi_kasus_get",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_kasus(
    narasi_id: str,
    service: Annotated[NarasiService, Depends(get_narasi_service)],
) -> NarasiKasusDetail:
    """Kasus + versi terbaru (dengan tautan sumber, tanpa teks sumber)."""
    kasus = service.get_kasus(narasi_id)
    terbaru = service.versi_terbaru(narasi_id)
    return NarasiKasusDetail(
        **kasus.model_dump(),
        versi_terbaru=_lengkap(service, terbaru) if terbaru else None,
    )


@router.get(
    "/{narasi_id}/riwayat",
    response_model=NarasiRiwayatRead,
    summary="Riwayat versi dan event kasus narasi (tim-kajian)",
    operation_id="narasi_kasus_riwayat",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def get_riwayat(
    narasi_id: str,
    service: Annotated[NarasiService, Depends(get_narasi_service)],
) -> NarasiRiwayatRead:
    """Seluruh versi (urut `revision_no`) dan event (urut waktu)."""
    service.get_kasus(narasi_id)
    return NarasiRiwayatRead(
        versi=[_lengkap(service, v) for v in service.daftar_versi(narasi_id)],
        event=service.daftar_event(narasi_id),
    )


@router.post(
    "/{narasi_id}/revisi",
    response_model=NarasiVersiRead,
    response_model_exclude={"metadata_ai"},
    status_code=201,
    summary="Tulis revisi manual bersumber (tim-kajian)",
    operation_id="narasi_kasus_revisi",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        409: {"model": ErrorResponse, "description": "supersedes_id basi (versi_basi)."},
        422: {"model": ErrorResponse, "description": "Teks/sumber tidak valid."},
    },
)
def revisi_kasus(
    narasi_id: str,
    data: NarasiRevisiCreate,
    service: Annotated[NarasiService, Depends(get_narasi_service)],
    sumber_service: Annotated[NarasiSumberService, Depends(get_narasi_sumber_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> NarasiVersiRead:
    """Tambah versi `REVIEWER_EDIT` berstatus hasil `TEAM_REVIEW`.

    `source_hash` diisi server dari sumber tersimpan; `sumber_id` tak dikenal 422.
    """
    service.get_kasus(narasi_id)
    kutipan: list[KutipanSumber] = []
    for item in data.sumber:
        try:
            ref = sumber_service.get(item.sumber_id)
        except NotFoundError as exc:
            raise ValidationAppError(f"Sumber '{item.sumber_id}' tidak ditemukan.") from exc
        kutipan.append(
            KutipanSumber(
                sumber_id=item.sumber_id,
                source_hash=ref.teks_hash,
                basis_relation=item.basis_relation,
                source_span=item.source_span,
            )
        )

    def _aksi() -> NarasiVersiRead:
        return service.tambah_versi(
            narasi_id,
            revision_origin=RevisionOrigin.REVIEWER_EDIT,
            status_hasil=StatusNarasi.TEAM_REVIEW,
            teks=data.teks,
            sumber=kutipan,
            supersedes_id=data.supersedes_id,
            aktor=_aktor(principal),
        )

    return run_idempotent(idem, response, NarasiVersiRead, _aksi)
