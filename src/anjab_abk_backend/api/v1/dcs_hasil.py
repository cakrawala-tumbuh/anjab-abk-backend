"""Endpoint analisis dan hasil DCS."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path

from ...core.services.partisipan import PartisipanService
from ...dcs.schemas.hasil import DcsHasilRead, DcsHasilRespondenRead
from ...dcs.services.analisis import compute_hasil, compute_hasil_responden
from ...dcs.services.instrumen import DcsInstrumenService
from ...dcs.services.jawaban import DcsJawabanService
from ...dcs.services.responden import DcsRespondenService
from ...dependencies import (
    READ_GUARDS,
    authorize_responden_access,
    get_current_principal,
    get_dcs_instrumen_service,
    get_dcs_jawaban_service,
    get_dcs_responden_service,
    get_partisipan_service,
    get_wcp_jawaban_service,
    get_wcp_responden_service,
    rate_limit,
)
from ...errors import ValidationAppError
from ...schemas.common import ErrorResponse
from ...security import Principal
from ...wcp.seed import DIMENSI
from ...wcp.services.analisis import compute_hasil_responden as wcp_compute_responden
from ...wcp.services.jawaban import WcpJawabanService
from ...wcp.services.responden import WcpRespondenService

router = APIRouter()

_WRITE_GUARDS = [Depends(get_current_principal), Depends(rate_limit)]
_AUTH = {401: {"model": ErrorResponse, "description": "Token tidak ada/invalid."}}
_RATE = {429: {"model": ErrorResponse, "description": "Terlalu banyak permintaan."}}
_NOT_FOUND_RSP = {404: {"model": ErrorResponse, "description": "Responden tidak ditemukan."}}
_FORBIDDEN = {
    403: {"model": ErrorResponse, "description": "Bukan admin atau bukan pemilik responden."}
}

# Kode dimensi risiko WCP (is_risk=True): CH, SD, PI
_WCP_RISK_KODES = frozenset(kode for kode, _, _, is_risk in DIMENSI if is_risk)


def _compute_wcp_risk_score(
    wcp_rsp_service: WcpRespondenService,
    wcp_jwb_service: WcpJawabanService,
) -> float | None:
    """Skor risiko WCP ternormalisasi (0–1); `None` bila WCP belum punya responden submit."""
    submitted = [r for r in wcp_rsp_service.list_all() if r.sudah_submit]
    if not submitted:
        return None

    risk_scores: list[float] = []
    for rsp in submitted:
        raw = wcp_jwb_service.get_raw_by_responden(rsp.id)
        hasil = wcp_compute_responden(rsp.id, raw)
        for dim in hasil.dimensi:
            if dim.dimensi_kode in _WCP_RISK_KODES:
                # Dimensi risiko: skor tinggi = risiko tinggi; normalisasi ke 0–1
                risk_scores.append((dim.skor - 1.0) / 4.0)

    return round(sum(risk_scores) / len(risk_scores), 4) if risk_scores else 0.0


@router.post(
    "/analisis",
    response_model=DcsHasilRead,
    summary="Jalankan analisis DCS (CLOSED → ANALYZED)",
    operation_id="dcs_analisis",
    dependencies=_WRITE_GUARDS,
    responses={**_AUTH, **_RATE},
)
def run_analisis(
    instrumen_service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
    wcp_rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    wcp_jwb_service: Annotated[WcpJawabanService, Depends(get_wcp_jawaban_service)],
) -> DcsHasilRead:
    instrumen = instrumen_service.get()
    if instrumen.status not in ("CLOSED", "ANALYZED"):
        raise ValidationAppError(
            f"Analisis hanya dapat dijalankan saat instrumen berstatus CLOSED atau ANALYZED"
            f" (saat ini: {instrumen.status})."
        )

    responden_list = rsp_service.list_all()
    submitted = [r for r in responden_list if r.sudah_submit]

    if len(submitted) < instrumen.min_responden:
        raise ValidationAppError(
            f"Analisis membutuhkan minimal {instrumen.min_responden} responden yang sudah"
            f" submit, baru ada {len(submitted)}."
        )

    responden_raw: list[tuple[str, dict[str, int]]] = [
        (r.id, jwb_service.get_raw_by_responden(r.id)) for r in submitted
    ]

    wcp_risk = _compute_wcp_risk_score(wcp_rsp_service, wcp_jwb_service)

    if instrumen.status == "CLOSED":
        instrumen_service.set_analyzed()

    return compute_hasil(responden_raw, wcp_risk)


@router.get(
    "/hasil",
    response_model=DcsHasilRead,
    summary="Lihat hasil analisis instrumen DCS",
    operation_id="dcs_hasil",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE},
)
def get_hasil(
    instrumen_service: Annotated[DcsInstrumenService, Depends(get_dcs_instrumen_service)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
    wcp_rsp_service: Annotated[WcpRespondenService, Depends(get_wcp_responden_service)],
    wcp_jwb_service: Annotated[WcpJawabanService, Depends(get_wcp_jawaban_service)],
) -> DcsHasilRead:
    instrumen = instrumen_service.get()
    if instrumen.status != "ANALYZED":
        raise ValidationAppError(
            f"Hasil hanya tersedia setelah analisis dijalankan"
            f" (status saat ini: {instrumen.status})."
        )
    responden_list = rsp_service.list_all()
    submitted = [r for r in responden_list if r.sudah_submit]
    responden_raw: list[tuple[str, dict[str, int]]] = [
        (r.id, jwb_service.get_raw_by_responden(r.id)) for r in submitted
    ]

    wcp_risk = _compute_wcp_risk_score(wcp_rsp_service, wcp_jwb_service)

    return compute_hasil(responden_raw, wcp_risk)


@router.get(
    "/hasil-responden/{responden_id}",
    response_model=DcsHasilRespondenRead,
    summary="Lihat hasil analisis per responden DCS (admin atau pemilik)",
    operation_id="dcs_hasil_responden_get",
    dependencies=READ_GUARDS,
    responses={**_AUTH, **_RATE, **_FORBIDDEN, **_NOT_FOUND_RSP},
)
def get_hasil_responden(
    responden_id: Annotated[str, Path(description="ID responden.")],
    principal: Annotated[Principal, Depends(get_current_principal)],
    rsp_service: Annotated[DcsRespondenService, Depends(get_dcs_responden_service)],
    jwb_service: Annotated[DcsJawabanService, Depends(get_dcs_jawaban_service)],
    par_service: Annotated[PartisipanService, Depends(get_partisipan_service)],
) -> DcsHasilRespondenRead:
    responden = rsp_service.get(responden_id)
    authorize_responden_access(principal, responden.partisipan_id, par_service)
    if not responden.sudah_submit:
        raise ValidationAppError("Responden belum mengirimkan jawaban.")
    raw = jwb_service.get_raw_by_responden(responden_id)
    return compute_hasil_responden(responden_id, raw)
