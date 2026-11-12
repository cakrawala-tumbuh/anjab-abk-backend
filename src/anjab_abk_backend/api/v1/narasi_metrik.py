"""Metrik alur narasi UX-13: detak menit aktif tinjauan dan agregat metrik. Khusus `tim-kajian`."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from ...dependencies import (
    READ_GUARDS,
    get_current_principal,
    get_narasi_metrik_service,
    rate_limit,
    require_tim_kajian,
)
from ...narasi.schemas.kasus import NarrativeKind
from ...narasi.schemas.metrik import DESKRIPSI_METRIK, MetrikNarasiRead
from ...narasi.services.metrik import NarasiMetrikService
from ...schemas.common import ErrorResponse
from ...security import Principal

router = APIRouter()
router_metrik = APIRouter()

_READ = [*READ_GUARDS, Depends(require_tim_kajian)]
_WRITE = [Depends(require_tim_kajian), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_FORBIDDEN = {403: {"model": ErrorResponse, "description": "Bukan anggota grup tim-kajian."}}


@router.post(
    "/{narasi_id}/menit-aktif",
    status_code=204,
    response_class=Response,
    summary="Catat detak menit aktif tinjauan (tim-kajian)",
    description=(
        "Klien memanggil ini sekali per menit hanya saat layar tinjauan aktif. Server memotong "
        "waktu ke menit sendiri dan tidak menerima timestamp klien; detak ganda dalam menit "
        "yang sama dari orang yang sama menghasilkan satu baris."
    ),
    operation_id="narasi_menit_aktif_catat",
    dependencies=_WRITE,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        404: {"model": ErrorResponse, "description": "Kasus narasi tidak ditemukan."},
    },
)
def catat_menit_aktif(
    narasi_id: str,
    service: Annotated[NarasiMetrikService, Depends(get_narasi_metrik_service)],
    principal: Annotated[Principal, Depends(get_current_principal)],
) -> Response:
    """Catat satu menit aktif atas nama subjek token; idempoten per menit."""
    service.catat_menit_aktif(narasi_id, principal.subject)
    return Response(status_code=204)


@router_metrik.get(
    "",
    response_model=MetrikNarasiRead,
    summary="Metrik alur narasi (tim-kajian)",
    description=DESKRIPSI_METRIK,
    operation_id="narasi_metrik_get",
    dependencies=_READ,
    responses={
        **_AUTH,
        **_RATE,
        **_FORBIDDEN,
        422: {
            "model": ErrorResponse,
            "description": "Tanggal salah, `dari` > `sampai`, atau rentang > 366 hari.",
        },
    },
)
def get_metrik(
    service: Annotated[NarasiMetrikService, Depends(get_narasi_metrik_service)],
    dari: Annotated[date, Query(description="Tanggal awal inklusif (YYYY-MM-DD, UTC).")],
    sampai: Annotated[date, Query(description="Tanggal akhir inklusif (YYYY-MM-DD, UTC).")],
    narrative_kind: Annotated[
        NarrativeKind | None, Query(description="Saring per jenis narasi kasus.")
    ] = None,
) -> MetrikNarasiRead:
    """Hitung metrik agregat (cakupan sumber, tingkat koreksi/tolak, menit aktif) satu rentang."""
    return service.hitung(dari, sampai, narrative_kind)
