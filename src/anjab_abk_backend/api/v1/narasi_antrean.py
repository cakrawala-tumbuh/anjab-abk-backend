"""Antrean tinjauan Tim: daftar, detail berdampingan dengan sumber, dan satu keputusan per kasus.

Khusus `tim-kajian` (admin tidak otomatis lolos). Tanpa aksi massal; hasil `TERIMA` berhenti
di `TEAM_VERIFIED`.
"""

from __future__ import annotations

from typing import Annotated, Any

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
from ...narasi.schemas.antrean import (
    CATATAN_MIN,
    PAPARAN_TIDAK_BERLAKU,
    STATUS_ANTREAN,
    AksiTinjauan,
    AntreanDetailRead,
    AntreanItemRead,
    StatusAntrean,
    TinjauanCreate,
)
from ...narasi.schemas.kasus import EventKind, RevisionOrigin, StatusNarasi
from ...narasi.schemas.mesin import AktorNarasi, KutipanSumber, NarasiEventRead
from ...narasi.services.narasi import (
    NarasiService,
    NarasiTanpaTeksError,
    NarasiTidakDalamAntreanError,
)
from ...narasi.services.sumber import NarasiSumberService
from ...schemas.common import ErrorResponse, Page
from ...security import Principal
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()
router_tinjauan = APIRouter()

ROLE_TINJAUAN = "tim-kajian"
"""Peran yang dicatat pada event dan versi hasil tinjauan (ditetapkan issue, bukan dari body)."""

PEMETAAN_AKSI: dict[AksiTinjauan, EventKind] = {
    AksiTinjauan.TERIMA: EventKind.TEAM_APPROVE,
    AksiTinjauan.KOREKSI: EventKind.TEAM_REVISE,
    AksiTinjauan.TOLAK: EventKind.TEAM_REJECT,
    AksiTinjauan.BUTUH_SUMBER: EventKind.NEED_SOURCE,
}
"""Aksi reviewer -> jenis event tahap Tim."""

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Kasus narasi tidak ditemukan."}}


def _aktor(principal: Principal) -> AktorNarasi:
    """Turunkan aktor dari token tervalidasi; peran selalu `tim-kajian`."""
    return AktorNarasi(key=principal.subject, role=ROLE_TINJAUAN)


def _daftar(meta: dict[str, Any], kunci: str) -> list[Any]:
    """Ambil nilai list dari `metadata_ai`; selain list dianggap kosong."""
    nilai = meta.get(kunci)
    return nilai if isinstance(nilai, list) else []


@router.get(
    "",
    response_model=Page[AntreanItemRead],
    summary="Antrean tinjauan Tim (tanpa teks)",
    operation_id="narasi_antrean_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN},
)
def list_antrean(
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[NarasiService, Depends(get_narasi_service)],
    status: Annotated[StatusAntrean | None, Query(description="Filter status antrean.")] = None,
    instrument_id: Annotated[
        str | None, Query(max_length=50, description="Filter instrumen.")
    ] = None,
    periode: Annotated[str | None, Query(max_length=20, description="Filter periode.")] = None,
) -> Page[AntreanItemRead]:
    """Kasus `AI_DRAFT`, `TEAM_REVIEW`, `NEED_FACT`; urut `updated_at` naik."""
    items, total = service.list_antrean(
        status=status.value if status else None,
        instrument_id=instrument_id,
        periode=periode,
        limit=page.limit,
        offset=page.offset,
    )
    return Page[AntreanItemRead](items=items, total=total, limit=page.limit, offset=page.offset)


@router.get(
    "/{narasi_id}",
    response_model=AntreanDetailRead,
    summary="Detail antrean: draf berdampingan dengan teks sumber",
    operation_id="narasi_antrean_get",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        409: {
            "model": ErrorResponse,
            "description": "Kasus di luar antrean (narasi_tidak_dalam_antrean).",
        },
    },
)
def get_antrean(
    narasi_id: str,
    service: Annotated[NarasiService, Depends(get_narasi_service)],
) -> AntreanDetailRead:
    """Versi terbaru, sumber lengkap, dan metadata AI terpilih.

    `paparan` bernilai tetap `TIDAK_BERLAKU` (F1); `AiRunRead` dan keluaran mentah tidak dibuka.
    """
    kasus = service.get_kasus(narasi_id)
    if kasus.status not in STATUS_ANTREAN:
        raise NarasiTidakDalamAntreanError(f"Kasus berstatus {kasus.status.value}, bukan antrean.")
    versi = service.versi_terbaru(narasi_id)
    if versi is None:
        raise NarasiTidakDalamAntreanError("Kasus belum punya versi untuk ditinjau.")
    meta = versi.metadata_ai or {}
    return AntreanDetailRead(
        narasi_id=kasus.id,
        instrument_id=kasus.instrument_id,
        field_key=kasus.field_key,
        peran_ref=kasus.peran_ref,
        periode=kasus.periode,
        narrative_kind=kasus.narrative_kind,
        status=kasus.status,
        versi_id=versi.id,
        revision_no=versi.revision_no,
        revision_origin=versi.revision_origin,
        teks=versi.teks,
        ai_run_id=versi.ai_run_id,
        sumber=service.sumber_lengkap_versi(versi.id),
        contradictions=_daftar(meta, "contradictions"),
        unknowns=_daftar(meta, "unknowns"),
        missing_facts=_daftar(meta, "missing_facts"),
        claim_to_source_map=meta.get("claim_to_source_map"),
        recommended_review_scope=meta.get("recommended_review_scope"),
        paparan=PAPARAN_TIDAK_BERLAKU,
    )


@router_tinjauan.post(
    "/{narasi_id}/tinjauan",
    response_model=NarasiEventRead,
    status_code=201,
    summary="Catat satu keputusan tinjauan atas versi yang dilihat (tim-kajian)",
    operation_id="narasi_kasus_tinjauan",
    dependencies=_WRITE,
    responses={
        **IDEMPOTENCY_RESPONSES,
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        **_NOTFOUND,
        409: {
            "model": ErrorResponse,
            "description": (
                "versi_basi, narasi_tanpa_teks (TERIMA atas versi tanpa teks), atau transisi "
                "status tidak sah."
            ),
        },
        422: {
            "model": ErrorResponse,
            "description": "Catatan kurang (TOLAK/BUTUH_SUMBER) atau KOREKSI tak valid.",
        },
    },
)
def tinjau_kasus(
    narasi_id: str,
    data: TinjauanCreate,
    service: Annotated[NarasiService, Depends(get_narasi_service)],
    sumber_service: Annotated[NarasiSumberService, Depends(get_narasi_sumber_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> NarasiEventRead:
    """Terapkan satu aksi: `TERIMA`, `KOREKSI`, `TOLAK`, atau `BUTUH_SUMBER`.

    `KOREKSI` membuat versi `REVIEWER_EDIT` lalu event yang menunjuk versi baru dalam satu
    transaksi. `TERIMA` berhenti di `TEAM_VERIFIED` tanpa rilis/keputusan.
    """
    service.get_kasus(narasi_id)
    catatan = data.catatan.strip() if data.catatan else None
    if data.aksi in (AksiTinjauan.TOLAK, AksiTinjauan.BUTUH_SUMBER) and (
        catatan is None or len(catatan) < CATATAN_MIN
    ):
        raise ValidationAppError(f"catatan minimal {CATATAN_MIN} karakter untuk {data.aksi.value}.")
    kutipan: list[KutipanSumber] = []
    if data.aksi == AksiTinjauan.KOREKSI:
        if not data.teks or not data.sumber:
            raise ValidationAppError("KOREKSI wajib menyertakan teks dan sumber.")
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
    aktor = _aktor(principal)

    def _aksi() -> NarasiEventRead:
        versi_id = data.narasi_versi_id
        if data.aksi == AksiTinjauan.TERIMA:
            terbaru = service.versi_terbaru(narasi_id)
            if terbaru is not None and terbaru.id == versi_id and terbaru.teks is None:
                raise NarasiTanpaTeksError("Versi tanpa teks tidak dapat diterima.")
        elif data.aksi == AksiTinjauan.KOREKSI:
            baru = service.tambah_versi(
                narasi_id,
                revision_origin=RevisionOrigin.REVIEWER_EDIT,
                status_hasil=StatusNarasi.TEAM_REVIEW,
                teks=data.teks,
                sumber=kutipan,
                supersedes_id=versi_id,
                aktor=aktor,
            )
            versi_id = baru.id
        return service.catat_event(narasi_id, versi_id, PEMETAAN_AKSI[data.aksi], aktor, catatan)

    return run_idempotent(idem, response, NarasiEventRead, _aksi)
