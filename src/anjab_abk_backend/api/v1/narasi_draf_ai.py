"""Pengajuan draf AI atas kasus narasi F1 dan pembacaan statusnya (khusus `tim-kajian`).

Rute ini hanya mengajukan job; hasil run belum diserap ke narasi. Tanpa flag AI hidup,
`POST` menjawab 409 sebelum membaca apa pun dan tidak menulis baris di tabel mana pun.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import ValidationError

from ...ai.fungsi_p10 import ParameterP10
from ...ai.gateway import AiGateway
from ...ai.redaksi import SumberAi
from ...config import Settings, get_settings
from ...dependencies import (
    READ_GUARDS,
    Idempotency,
    Pagination,
    SessionDep,
    get_ai_gateway,
    get_current_principal,
    get_narasi_service,
    get_narasi_sumber_service,
    get_permintaan_ai_service,
    idempotency,
    pagination_params,
    rate_limit,
    require_tim_kajian,
)
from ...errors import ConflictError, NotFoundError, ValidationAppError
from ...fitur import FiturNonaktifError, ai_boleh_jalan
from ...narasi.schemas.kasus import StatusNarasi
from ...narasi.schemas.permintaan_ai import PermintaanAiCreate, PermintaanAiRead
from ...narasi.services.narasi import NarasiService
from ...narasi.services.permintaan_ai import PermintaanAiService
from ...narasi.services.sumber import NarasiSumberService
from ...schemas.common import ErrorResponse, FiturKode, Page
from ...security import Principal
from ..concurrency import IDEMPOTENCY_RESPONSES, run_idempotent

router = APIRouter()

KODE_FUNGSI = "P10"
"""Fungsi AI yang diajukan rute ini (draf narasi formal F1)."""

STATUS_BOLEH_AJUKAN = frozenset({StatusNarasi.SOURCE_CHECKED, StatusNarasi.NEED_FACT})
"""Status kasus yang boleh diajukan ke AI."""

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}
_NOTFOUND = {404: {"model": ErrorResponse, "description": "Kasus narasi tidak ditemukan."}}


class PiiModeBelumDidukungError(ConflictError):
    """409: `AI_PII_MODE` bukan `BLOKIR` (mode `SAMARKAN` belum dibuka)."""

    error_code = "pii_mode_belum_didukung"


class NarasiStatusTidakSahError(ConflictError):
    """409: status kasus di luar `SOURCE_CHECKED`/`NEED_FACT`."""

    error_code = "narasi_status_tidak_sah"


class PermintaanBerjalanError(ConflictError):
    """409: kasus masih punya permintaan AI yang belum diserap."""

    error_code = "permintaan_berjalan"


class IzinSumberTidakAdaError(ConflictError):
    """409: sumber yang diajukan tidak berizin AI (`izin_ai=false`)."""

    error_code = "izin_sumber_tidak_ada"


class FungsiBelumAktifError(ConflictError):
    """409: fungsi P10 belum terdaftar (`AI_FUNGSI_AKTIF`)."""

    error_code = "fungsi_belum_aktif"


@router.post(
    "/{narasi_id}/draf-ai",
    response_model=PermintaanAiRead,
    status_code=202,
    summary="Ajukan draf AI atas kasus narasi (tim-kajian)",
    operation_id="narasi_kasus_draf_ai_ajukan",
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
                "feature_disabled; pii_mode_belum_didukung; narasi_status_tidak_sah; "
                "permintaan_berjalan; izin_sumber_tidak_ada; fungsi_belum_aktif."
            ),
        },
        422: {"model": ErrorResponse, "description": "sumber_id tak dikenal / parameter tak sah."},
    },
)
def ajukan_draf_ai(
    narasi_id: str,
    data: PermintaanAiCreate,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    service: Annotated[NarasiService, Depends(get_narasi_service)],
    sumber_service: Annotated[NarasiSumberService, Depends(get_narasi_sumber_service)],
    permintaan: Annotated[PermintaanAiService, Depends(get_permintaan_ai_service)],
    gateway: Annotated[AiGateway, Depends(get_ai_gateway)],
    principal: Annotated[Principal, Depends(get_current_principal)],
    idem: Annotated[Idempotency, Depends(idempotency)],
    response: Response,
) -> PermintaanAiRead:
    """Ajukan job P10 atas satu kasus; tautan kasus dan `ai_run` dicatat di tabel permintaan.

    Urutan periksa mengikat: flag/saklar AI (sebelum membaca apa pun), mode PII, kasus,
    status, permintaan berjalan, sumber dikenal, sumber berizin AI, lalu pengajuan.
    """
    if not ai_boleh_jalan(session, settings, FiturKode.AI_NARRATIVE_DRAFT):
        raise FiturNonaktifError(FiturKode.AI_NARRATIVE_DRAFT)
    if settings.ai_pii_mode != "BLOKIR":
        raise PiiModeBelumDidukungError("Hanya AI_PII_MODE=BLOKIR yang didukung.")
    kasus = service.get_kasus(narasi_id)
    if kasus.status not in STATUS_BOLEH_AJUKAN:
        raise NarasiStatusTidakSahError(
            f"Kasus berstatus {kasus.status.value}; hanya SOURCE_CHECKED atau NEED_FACT."
        )
    if permintaan.ada_belum_diserap(narasi_id):
        raise PermintaanBerjalanError("Kasus masih punya permintaan AI yang belum diserap.")

    sumber_ids = list(dict.fromkeys(data.sumber_ids))
    sumber = []
    for sid in sumber_ids:
        try:
            sumber.append(sumber_service.get(sid))
        except NotFoundError as exc:
            raise ValidationAppError(f"Sumber '{sid}' tidak ditemukan.") from exc
    tanpa_izin = [s.id for s in sumber if not s.izin_ai]
    if tanpa_izin:
        daftar = ", ".join(tanpa_izin[:5]) + ("..." if len(tanpa_izin) > 5 else "")
        raise IzinSumberTidakAdaError(f"Sumber tanpa izin AI: {daftar}.")
    try:
        parameter = ParameterP10(
            narrative_kind=kasus.narrative_kind.value,  # type: ignore[arg-type]
            instrument_id=kasus.instrument_id,
            field_key=kasus.field_key,
            periode=kasus.periode,
        ).model_dump(mode="json")
    except ValidationError as exc:
        raise ValidationAppError(
            "Lingkup kasus (instrument_id, field_key, periode) tidak sesuai pola parameter AI."
        ) from exc
    calon = [
        SumberAi(source_id=s.id, source_hash=s.teks_hash, jenis=s.jenis.value, teks=s.teks)
        for s in sumber
    ]

    def _aksi() -> PermintaanAiRead:
        try:
            job = gateway.ajukan(KODE_FUNGSI, calon, parameter, None, principal.subject)
        except NotFoundError as exc:
            raise FungsiBelumAktifError(f"Fungsi AI {KODE_FUNGSI} belum diaktifkan.") from exc
        return permintaan.catat(narasi_id, job.id, job.ref_id or "", sumber_ids, principal.subject)

    return run_idempotent(idem, response, PermintaanAiRead, _aksi)


@router.get(
    "/{narasi_id}/permintaan-ai",
    response_model=Page[PermintaanAiRead],
    summary="Daftar permintaan draf AI atas kasus narasi (tim-kajian)",
    operation_id="narasi_kasus_permintaan_ai_list",
    dependencies=_READ,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOTFOUND},
)
def list_permintaan_ai(
    narasi_id: str,
    page: Annotated[Pagination, Depends(pagination_params)],
    service: Annotated[NarasiService, Depends(get_narasi_service)],
    permintaan: Annotated[PermintaanAiService, Depends(get_permintaan_ai_service)],
) -> Page[PermintaanAiRead]:
    """Permintaan terbaru dulu beserta status job; tanpa `masukan` dan `keluaran`."""
    service.get_kasus(narasi_id)
    items, total = permintaan.list_by_narasi(narasi_id, limit=page.limit, offset=page.offset)
    return Page[PermintaanAiRead](items=items, total=total, limit=page.limit, offset=page.offset)
